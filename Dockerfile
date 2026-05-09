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

# Pre-download PaddleOCR models during build to avoid runtime downloads
RUN python -c "from paddleocr import PaddleOCR; PaddleOCR(lang='id', ocr_version='PP-OCRv4', use_gpu=False, enable_mkldnn=False, use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=False, show_log=False)"

COPY . .

CMD ["python", "scrapers/lotte.py"]
