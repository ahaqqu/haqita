# Qwen3-VL OCR for Product Promo Extraction

Extracts product names, brands, prices, and promo periods from brochure images using Qwen3-VL 2B via Ollama.

## Prerequisites

1. **Install Ollama**
   - Download from: https://ollama.com/download/windows
   - Ensure `ollama` is in your system PATH

2. **Pull the Model**
   ```bash
   ollama pull qwen3-vl:2b
   ```

3. **Install Python Dependencies**
   ```bash
   pip install requests Pillow
   ```

## Usage

### Via the launch menu (recommended)
```cmd
haqita.bat
```
Then select option **2** (Run Qwen3-VL OCR on local images).

### Direct
```cmd
scripts\run_qwen_ocr.bat
```

### Manual
```cmd
python scripts/qwen_ocr_processor.py
```

## Input

Place your promo images in `data/test/lotte/image-brochure/`. Supported formats: `.jpg`, `.jpeg`, `.png`, `.bmp`, `.webp`.

## Output

Results saved to `output/product_prices_YYYYMMDD_HHMMSS.json`:

```json
{
  "ht2.jpeg": {
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

Each run creates a new timestamped file — previous results are never overwritten. Results are written incrementally after each image, so a crash mid-run preserves partial results.

## How It Works

| Step | Description |
|---|---|
| Load image | Reads from `image-brochure/` folder |
| First pass | Describes the image freely (no format constraints) |
| Second pass | Converts the description to structured JSON |
| Retry | Up to 3 attempts with chat context on failure |
| Save | Timestamped JSON + debug log |

Both Indonesian and English text in brochures are supported.

## File Structure

| Path | Purpose |
|---|---|
| `scripts/qwen_ocr_processor.py` | Main OCR script |
| `scripts/run_qwen_ocr.bat` | Batch launcher |
| `data/test/lotte/image-brochure/` | Input images |
| `output/product_prices_*.json` | Extracted product data |
| `output/qwen_debug_*.log` | Debug logs |

## Requirements

- Python 3.8+
- `requests` + `Pillow` libraries
- Ollama 0.12.7+ with `qwen3-vl:2b` pulled
- NVIDIA GPU recommended (~3.3 GiB VRAM), works on CPU (~2 min/image on i9)
