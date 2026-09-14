import os
import pickle
import threading
from datetime import datetime

from docx import Document
import numpy as np
import requests
import torch
from pypdf import PdfReader
from rank_bm25 import BM25Okapi
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer, CrossEncoder

PDF_FOLDER = os.path.join(os.path.dirname(__file__), "data")
CACHE_PATH = os.path.join(os.path.dirname(__file__), "index_cache.pkl")

CHUNK_SIZE = 600
CHUNK_OVERLAP = 200

EMBED_MODEL_NAME = "Qwen/Qwen3-Embedding-0.6B"
RERANKER_MODEL_NAME = "BAAI/bge-reranker-v2-m3"

LLM_PROVIDER = "openai"
LLM_PROVIDER = "gemini"

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen2.5:7b"

OPENAI_MODEL = "gpt-4o-mini"
GEMINI_MODEL = "gemini-3.6-flash"
# GEMINI_MODEL = "gemini-2.5-pro"
# GEMINI_MODEL = "gemini-3.5-flash"
# GEMINI_MODEL = "gemini-3.6-flash"
# GEMINI_MODEL = "gemini-3.7-flash"
# GEMINI_MODEL = "gemini-3.8-flash"
# GEMINI_MODEL = "gemini-flash-latest"

ALPHA = 0.1
INITIAL_K = 30
FINAL_K = 5

RELEVANCE_THRESHOLD = 0.3

device = "cuda" if torch.cuda.is_available() else "cpu"

class RagPipeline:
    def __init__(self):
        self.embed_model = SentenceTransformer(EMBED_MODEL_NAME, device=device)
        self.cross_encoder = CrossEncoder(RERANKER_MODEL_NAME, device=device)

        self.chunks = []
        self.chunk_embeddings = None
        self.bm25 = None
        self._index_lock = threading.Lock()  #cegah race condition kalau ada 2 upload/rebuild bersamaan

        self._load_or_build_index()

    def _load_or_build_index(self):
        if os.path.exists(CACHE_PATH):
            with open(CACHE_PATH, "rb") as f:
                cache = pickle.load(f)
            self.chunks = cache["chunks"]
            self.chunk_embeddings = cache["chunk_embeddings"]
            tokenized = [c.lower().split() for c in self.chunks]
            self.bm25 = BM25Okapi(tokenized)
            print(f"[rag_pipeline] {len(self.chunks)} chunk dimuat dari cache")
            return
        self._build_index_from_pdfs()

    def _build_index_from_pdfs(self):
        if not os.path.isdir(PDF_FOLDER):
            raise FileNotFoundError(f"Folder PDF tidak ditemukan: {PDF_FOLDER}. ")

        documents = []
        for filename in os.listdir(PDF_FOLDER):
            if not filename.endswith((".pdf", ".docx", ".txt")):
                continue
            documents.extend(self._extract_chunks(os.path.join(PDF_FOLDER, filename), filename))

        if not documents:
            raise ValueError("Tidak ada dokumen ditemukan di folder 'data/'.")

        self.chunks = [d["text"] for d in documents]
        print(f"[rag_pipeline] Total chunk: {len(self.chunks)}")

        self.bm25 = BM25Okapi([c.lower().split() for c in self.chunks])
        self.chunk_embeddings = self.embed_model.encode(
            self.chunks, convert_to_numpy=True, normalize_embeddings=True,
            show_progress_bar=True,
        )
        self._save_cache()

    @staticmethod
    def _extract_chunks(filepath, filename):
        """ekstrak teks satu PDF lalu potong jadi chunk. dipake bsaat build awal atau saat 
        ada upload dokumen baru, biar logic-nya gak dobel."""
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
        )
        if filename.endswith(".pdf"):
            reader = PdfReader(filepath)
        elif filename.endswith(".docx"):
            doc = Document(filepath)
            reader = [page.text for page in doc.pages]
        else:
            with open(filepath, "r", encoding="utf-8") as f:
                reader = [f.read()]

        text = ""
        for page in reader:
            if isinstance(page, str):
                text += page + "\n"
            else:
                text += page.extract_text() + "\n"

        return [
            {"id": f"{filename}_chunk_{i}", "text": chunk}
            for i, chunk in enumerate(splitter.split_text(text))
        ]

    def _save_cache(self):
        with open(CACHE_PATH, "wb") as f:
            pickle.dump(
                {"chunks": self.chunks, "chunk_embeddings": self.chunk_embeddings}, f
            )

    def add_document(self, filepath, filename):
        new_docs = self._extract_chunks(filepath, filename)
        if not new_docs:
            raise ValueError(
                f"Tidak ada teks yang bisa diekstrak dari '{filename}'. "
                "Kemungkinan dokumen ini hasil scan/gambar tanpa lapisan teks."
            )

        new_chunks = [d["text"] for d in new_docs]
        new_embeddings = self.embed_model.encode(
            new_chunks, convert_to_numpy=True, normalize_embeddings=True,
        )

        with self._index_lock:
            self.chunks.extend(new_chunks)
            self.chunk_embeddings = (
                new_embeddings
                if self.chunk_embeddings is None
                else np.vstack([self.chunk_embeddings, new_embeddings])
            )
            self.bm25 = BM25Okapi([c.lower().split() for c in self.chunks])
            self._save_cache()

        print(f"[rag_pipeline] '{filename}' ditambahkan: {len(new_chunks)} chunk baru, "
              f"total sekarang {len(self.chunks)} chunk.")
        return len(new_chunks)

    @staticmethod
    def _normalize(arr):
        if arr.max() == arr.min():
            return np.zeros_like(arr)
        return (arr - arr.min()) / (arr.max() - arr.min())

    def hybrid_search(self, query, top_k=INITIAL_K, alpha=ALPHA):
        query_emb = self.embed_model.encode(
            [query], convert_to_numpy=True, normalize_embeddings=True
        )[0]
        semantic_scores = self.chunk_embeddings @ query_emb
        bm25_scores = np.array(self.bm25.get_scores(query.lower().split()))
        combined = alpha * self._normalize(semantic_scores) + (1 - alpha) * self._normalize(
            bm25_scores
        )
        ranked = np.argsort(combined)[::-1][:top_k]
        return [(idx, combined[idx]) for idx in ranked]

    def retrieve_and_rerank(self, query, initial_k=INITIAL_K, final_k=FINAL_K):
        initial_results = self.hybrid_search(query, top_k=initial_k)
        candidate_indices = [idx for idx, _ in initial_results]
        pairs = [[query, self.chunks[idx]] for idx in candidate_indices]
        rerank_scores = self.cross_encoder.predict(pairs)
        reranked = sorted(
            zip(candidate_indices, rerank_scores), key=lambda x: x[1], reverse=True
        )
        return reranked[:final_k]

    #setting prompt untuk LLM, tergantung skor relevansi. Kalau rendah, jangan paksa jawab dari dokumen PDF.
    def _build_prompt(self, query, retrieved_chunks, best_score):
        today = datetime.now().strftime("%A, %d %B %Y")

        if best_score < RELEVANCE_THRESHOLD:
            # Skor relevansi rendah -> anggap ini sapaan/obrolan umum
            # jawab dari konteks PDF. Biarkan LLM jawab natural pakai pengetahuan umum.
            return f"""Kamu adalah asisten AI yang ramah dan natural, mirip ChatGPT/Gemini/Claude.
Hari ini: {today}.
Jawab pertanyaan berikut dengan natural pakai pengetahuan umum kamu.
Jangan menyebut "konteks" atau "dokumen" karena pertanyaan ini tidak berkaitan dengan dokumen tertentu.

Pertanyaan: {query}
Jawaban:"""

        context = "\n\n".join(retrieved_chunks)
        return f"""Kamu adalah asisten AI yang ramah dan punya akses ke dokumen referensi di bawah ini.
Hari ini: {today}.
Gunakan konteks berikut sebagai sumber utama untuk menjawab. Untuk fakta spesifik
yang menyangkut isi dokumen, jawab HANYA berdasarkan konteks ini dan jangan mengarang;
kalau tidak ada di konteks, katakan dengan jujur bahwa informasinya tidak ditemukan.
Untuk bagian pertanyaan yang bersifat umum (di luar isi dokumen), boleh pakai
pengetahuan umum kamu sendiri.

Konteks:
{context}

Pertanyaan: {query}
Jawaban:"""

    def generate_answer(self, query, retrieved_chunks, best_score):
        prompt = self._build_prompt(query, retrieved_chunks, best_score)

        if LLM_PROVIDER == "openai":
            return self._generate_openai(prompt)
        elif LLM_PROVIDER == "gemini":
            return self._generate_gemini(prompt)
        else:
            return self._generate_ollama(prompt)

    def _generate_ollama(self, prompt):
        try:
            response = requests.post(
                OLLAMA_URL,
                json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
                timeout=120,
            )
            response.raise_for_status()
            return response.json()["response"].strip()
        except requests.exceptions.ConnectionError:
            return (
                "Tidak bisa terhubung ke Ollama "
                f"(`ollama pull {OLLAMA_MODEL}`)."
            )

    def _generate_openai(self, prompt):
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return "OPENAI_API_KEY belum belum ada"
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            return f"Gagal memanggil OpenAI API: {e}"

    def _generate_gemini(self, prompt):
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            return "GEMINI_API_KEY belum ada"
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=GEMINI_MODEL, contents=prompt
            )
            return response.text.strip()
        except Exception as e:
            return f"Gagal memanggil Gemini API: {e}"

    def ask(self, query):
        #retrieve top-k dokumen, rerank
        reranked = self.retrieve_and_rerank(query)
        retrieved_texts = [self.chunks[idx] for idx, _ in reranked]
        best_score = max((score for _, score in reranked), default=-999)
        # print(f"[rag_pipeline] best rerank score = {best_score:.4f}")  # bantu nyari angka threshold yang pas
        #generate jawaban pakai LLM
        return self.generate_answer(query, retrieved_texts, best_score)