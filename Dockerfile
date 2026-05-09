FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libsm6 \
    libxrender1 \
    libxext6 \
    libgl1 \
    libgomp1 \
    ccache \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Pre-download PaddleOCR models at container startup (first run only)
# We do this at runtime instead of build time to avoid MKLDNN crashes during docker build
ENTRYPOINT ["bash", "-c", "python -c \"import os; from scrapers.lotte import get_paddle_ocr; print('Checking models...'); get_paddle_ocr(); print('Models ready.')\" && python scrapers/lotte.py"]
