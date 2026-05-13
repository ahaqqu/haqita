# Qwen3-VL OCR for Product Promo Extraction

This tool uses Qwen3-VL 2B (via Ollama) to intelligently extract product names, brands, prices, and promo periods from brochure/promo images, solving the text grouping issues found in traditional OCR like PaddleOCR.

## Prerequisites

1. **Install Ollama**
   - Download and install from: https://ollama.com/download/windows
   - Ensure `ollama` is added to your system PATH

2. **Pull the Model**
   ```bash
   ollama pull qwen3-vl:2b
   ```

3. **Install Python Dependencies**
   ```bash
   pip install requests Pillow
   ```

## Usage

1. **Place Images**: Put your promo images in the `data/test/lotte/` folder.

2. **Run the Extractor**:
   Double-click `run_qwen_ocr.bat` or run via terminal:
   ```cmd
   run_qwen_ocr.bat
   ```

3. **View Results**:
   Results are saved to `output/product_prices_YYYYMMDD_HHMMSS.json` with a unique timestamp per run.
   Each run creates a new file — previous results are never overwritten.
   Results are written incrementally, so if processing fails mid-way, partial results are preserved.

## Output Format

```json
{
  "ht1.jpeg": {
    "products": [
      {
        "brand": "AICE",
        "product": "Sandwich Cookies Panda",
        "price": "39.900",
        "unit": "6 x 45 ml",
        "promo": "BUY 1 GET 1"
      }
    ],
    "count": 5,
    "promo_period": "7 - 20 Mei 2026"
  }
}
```

## Files

| File | Purpose |
|---|---|
| `qwen_ocr_processor.py` | Main OCR script |
| `run_qwen_ocr.bat` | Batch file — auto-starts Ollama and runs the processor |
| `output/product_prices_*.json` | Extracted product data (timestamped, never overwritten) |
| `output/qwen_debug_*.log` | Debug logs (timestamped) |
| `data/test/lotte/` | Place your promo images here |

## Requirements

- Python 3.8+
- `requests` and `Pillow` libraries
- Ollama 0.12.7+ with qwen3-vl:2b pulled
- NVIDIA GPU recommended (uses ~3.3 GiB VRAM), but works on CPU
