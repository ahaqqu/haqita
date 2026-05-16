FROM python:3.12-slim

# System deps for sentence-transformers build (gcc for compiling C extensions)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps — install first for Docker layer caching
COPY docker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Default command: run consolidation pipeline
CMD ["python", "scripts/consolidate.py"]
