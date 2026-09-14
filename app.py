import os

from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename

from rag_pipeline import RagPipeline, PDF_FOLDER

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  #batas upload 20 MB per file
CORS(app)

pipeline = RagPipeline()
print("selesai, buka url http://localhost:5000")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(force=True)
    query = (data.get("message") or "").strip()

    if not query:
        return jsonify({"error": "Pesan kosong"}), 400

    try:
        answer = pipeline.ask(query)
        return jsonify({"answer": answer})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"error": "Tidak ada file yang dikirim"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "Nama file kosong"}), 400

    if not file.filename.lower().endswith((".pdf", ".docx", ".txt")):
        return jsonify({"error": "Saat ini hanya file PDF, DOCX, dan TXT yang didukung"}), 400

    filename = secure_filename(file.filename)
    filepath = os.path.join(PDF_FOLDER, filename)

    if os.path.exists(filepath):
        return jsonify({"error": f"File '{filename}' sudah pernah diupload"}), 409

    os.makedirs(PDF_FOLDER, exist_ok=True)
    file.save(filepath)

    try:
        n_chunks = pipeline.add_document(filepath, filename)
    except Exception as e:
        if os.path.exists(filepath):
            os.remove(filepath)
        return jsonify({"error": str(e)}), 500

    return jsonify({
        "message": f"'{filename}' berhasil diupload dan diindeks ({n_chunks} chunk).",
        "filename": filename,
        "chunks_added": n_chunks,
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    app.run(host="0.0.0.0", port=port, debug=False)