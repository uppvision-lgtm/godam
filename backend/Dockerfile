# ============================================================
# Docker image untuk Hugging Face Spaces
# Menjalankan FastAPI API + Celery worker dalam SATU kontainer
# (Hugging Face Spaces = 1 kontainer per Space)
# ============================================================
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Salin requirements dulu (biar caching pip lebih efisien)
COPY requirements.txt ./

# Install dependency Python
RUN pip install --no-cache-dir -r requirements.txt

# Install browser Chromium beserta dependency sistem yang dibutuhkan Playwright
RUN playwright install --with-deps chromium

# Salin seluruh source backend (main.py, tasks.py, live_session.py, dll.)
COPY . .

# Beri izin eksekusi pada script start
RUN chmod +x start.sh

# Hugging Face Spaces selalu memakai port 7860
EXPOSE 7860

CMD ["./start.sh"]
