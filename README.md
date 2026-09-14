---
title: Petra Assistant API
emoji: 🤖
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---

# Petra Assistant — Personal RAG Chatbot

Chatbot berbasis **Retrieval-Augmented Generation (RAG)** yang menjawab pertanyaan tentang latar belakang, pengalaman, dan riset saya (Petra Andhika Natanael) berdasarkan dokumen referensi (CV, ringkasan riset skripsi TrackNetV3, dll).

---

![Screenshot Petra Assistant](assets/visual.png)

---
## Fitur Utama

- **Hybrid Retrieval** — menggabungkan pencarian semantik (dense embedding) dan leksikal (BM25) untuk hasil retrieval yang lebih robust dibanding hanya mengandalkan satu metode.
- **Cross-Encoder Reranking** — kandidat hasil retrieval awal di-rerank ulang dengan cross-encoder agar urutan relevansi lebih akurat sebelum dikirim ke LLM.
- **Relevance-Aware Prompting** — sistem mendeteksi apakah pertanyaan relevan dengan isi dokumen (via skor reranking) atau sekadar obrolan umum, lalu menyesuaikan prompt LLM secara dinamis.
- **Multi-Provider LLM** — mendukung 3 backend generasi jawaban yang bisa ditukar lewat konfigurasi: **Ollama** (lokal, privat, gratis), **OpenAI**, dan **Gemini**.
- **Live Document Ingestion** — dokumen baru (PDF/DOCX/TXT) bisa diupload lewat UI dan langsung diindeks ke pipeline tanpa restart server.
- **Index Caching** — hasil embedding disimpan ke cache lokal (`index_cache.pkl`) supaya tidak perlu re-embed dari nol setiap kali server dijalankan.
- **Web UI Interaktif** — antarmuka chat berbasis Flask + vanilla JS dengan rendering Markdown, quick-suggestion pills, dan upload file.

---

## Arsitektur & Model yang Digunakan

Pipeline RAG terdiri dari 4 tahap:

```
Dokumen (PDF/DOCX/TXT)
      │  chunking
      ▼
Text Chunks ──► Embedding (dense) + BM25 (sparse)
      │
      ▼
Hybrid Search (weighted combination) ──► Top-K kandidat
      │
      ▼
Cross-Encoder Reranking ──► Top-N chunk paling relevan
      │
      ▼
LLM Generation (kontekstual, threshold-aware) ──► Jawaban
```

| Komponen | Model / Library | Keterangan |
|---|---|---|
| Text splitting | `RecursiveCharacterTextSplitter` (LangChain) | chunk size 600, overlap 200 karakter |
| Embedding model | `Qwen/Qwen3-Embedding-0.6B` (Sentence-Transformers) | representasi dense untuk semantic search |
| Sparse retrieval | `BM25Okapi` (rank_bm25) | pencarian leksikal berbasis term-frequency |
| Fusi skor | Weighted min-max normalization | `alpha` mengatur bobot semantic vs BM25 |
| Reranker | `BAAI/bge-reranker-v2-m3` (CrossEncoder) | re-scoring pasangan (query, chunk) untuk presisi lebih tinggi |
| LLM generation | Ollama (`qwen2.5:7b`, GGUF 4-bit) / OpenAI (`gpt-4o-mini`) / Gemini | dapat ditukar via konfigurasi, tanpa mengubah logic retrieval |
| Ekstraksi dokumen | `pypdf`, `python-docx` | mendukung PDF, DOCX, TXT |
| Backend | Flask | REST API (`/api/chat`, `/api/upload`) |
| Frontend | HTML/CSS/JS vanilla + Marked.js | rendering Markdown di jawaban chatbot |

**Alasan desain retrieval hybrid:** BM25 unggul untuk pencocokan kata kunci/istilah teknis yang eksak (misalnya nama proyek, angka, istilah spesifik), sedangkan embedding semantic menangkap kemiripan makna meski kata berbeda. Bobot `ALPHA` di-tuning agar BM25 lebih diandalkan (`ALPHA=0.1`) karena karakteristik dokumen (CV & ringkasan riset) yang padat istilah spesifik.

**Alasan desain threshold relevansi:** skor terbaik hasil reranking dibandingkan dengan `RELEVANCE_THRESHOLD`. Jika di bawah ambang, sistem menganggap pertanyaan bersifat obrolan umum (bukan tentang isi dokumen) dan membiarkan LLM menjawab dari pengetahuan umum tanpa memaksakan konteks dokumen yang tidak relevan — mencegah halusinasi akibat "menempelkan" konteks yang salah.

---

## Struktur Proyek

```
rag-chatbot/
├── app.py                 # Flask app: routing & API endpoint
├── rag_pipeline.py         # Inti pipeline RAG (retrieval, reranking, generation)
├── requirements.txt
├── data/                  # Folder dokumen sumber (PDF/DOCX/TXT)
├── index_cache.pkl        # Cache embedding (dibuat otomatis, jangan commit ke git)
├── templates/
│   └── index.html
└── static/
    ├── script.js
    └── style.css
```

---
