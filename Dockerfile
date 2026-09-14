FROM python:3.10-slim

WORKDIR /app

# Install dependencies dulu (supaya di-cache, build ulang lebih cepat kalau cuma ganti kode)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy semua kode project
COPY . .

# Hugging Face Spaces wajib pakai port 7860
EXPOSE 7860

CMD ["python", "app.py"]