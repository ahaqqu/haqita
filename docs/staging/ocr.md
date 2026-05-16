# Stage 2: OCR

Extracts product data from brochure images using Gemini or Ollama vision models.

## Overview

| | |
|---|---|
| **Input** | Brochure images in `database/scrape/<store>/<YYYYMMDD>/` |
| **Output** | `database/ocr/<store>/<store>_promos_YYYYMMDD_HHMMSS.json` |
| **State** | `database/ocr/<store>/state.json` — tracks OCR'd images to avoid re-processing |
| **Dry-run** | Prints extracted products without saving JSON |

## How It Works

1. Scan `database/scrape/<store>/` for image files (JPG/PNG/WebP)
2. Compare filenames against state file — skip already-processed images
3. For each new image:
   - Optionally preprocess (upscale, enhance contrast/sharpness for Ollama)
   - Send to configured OCR provider (Gemini or Ollama)
   - Parse JSON response into product dicts
   - Validate products (price range, name length)
   - Reject invalid products with reason
4. Write results to `database/ocr/<store>/`
5. Update state file with processed filenames

## OCR Output Schema

```json
{
  "store": "Lotte",
  "scraped_at": "2026-05-14T07:39:37",
  "source_url": "https://www.lottemart.co.id/all-promo-mart",
  "images_processed": 6,
  "ocr_provider": "gemini",
  "products": [
    {
      "name": "Indomie Goreng",
      "brand": "Indomie",
      "unit": "85 g",
      "price": 3500,
      "promo": "DAPAT 5 pcs",
      "period": "7 - 20 Mei 2026",
      "image_source": "promo_lotte_abc123.jpg",
      "ocr_raw_price": "Rp 3.500",
      "ocr_confidence": 0.91,
      "image_path": "database/scrape/lotte/20260516/promo_abc123.jpg"
    }
  ],
  "rejected": [
    { "raw": { "name": "...", "price": 0 }, "reason": "price_invalid: 0", "image_source": "..." }
  ],
  "stats": {
    "products_extracted": 42,
    "products_rejected": 2,
    "images_failed_ocr": 1
  }
}
```

## Product Schema

| Field | Type | Description |
|---|---|---|
| `name` | string | Product name |
| `brand` | string\|null | Brand name (uppercase) |
| `unit` | string\|null | Quantity (e.g., "85 g", "6 x 45 ml") |
| `price` | int | Price in IDR |
| `promo` | string\|null | Promo text (e.g., "DAPAT 5 pcs") |
| `period` | string\|null | Promo period (e.g., "7 - 20 Mei 2026") |
| `image_source` | string | Source image filename |
| `ocr_raw_price` | string | Raw price text from OCR |
| `ocr_confidence` | float | Confidence score (0.0–1.0) |
| `image_path` | string | Relative path to source image |

## OCR Providers

Configured in `config.yaml`:

```yaml
ocr:
  provider: gemini  # or "ollama"

  ollama:
    model: qwen3-vl:7b
    num_ctx: 8192
    timeout_seconds: 300
    max_retries: 2
    temperature: 0
    preprocess: true
    image_min_width_px: 1400
    image_contrast_enhance: 1.4
    image_sharpness_enhance: 1.2

  gemini:
    model: gemini-3-flash-preview
    timeout_seconds: 60
    max_retries: 2
```

Switch via `.env`:
```env
OCR_PROVIDER=gemini   # or "ollama"
GEMINI_API_KEY=your_key_here
```

## Validation Rules

Products are rejected if:
- Price is 0, negative, or outside valid range (`validation.min_price` to `validation.max_price`)
- Product name is too short (`validation.min_product_name_length`)
- Price cannot be parsed as integer

Products with low OCR confidence (`< validation.ocr_confidence_flag_threshold`) are flagged for review but not rejected.

## Usage

Via `haqita.bat` → Option [3] → OCR submenu:

| Choice | Action |
|---|---|
| **1** | OCR all images (both stores) |
| **2** | OCR Lotte images |
| **3** | OCR Superindo images |
| **4** | OCR specific image |
| **5** | Dry-run (report products without saving) |

## State File

`database/ocr/<store>/state.json`:

```json
{
  "processed": ["promo_abc123.jpg", "promo_def456.jpg"],
  "last_run": "2026-05-16T11:00:00"
}
```

## Output Structure

```
database/ocr/
├── lotte/
│   ├── state.json
│   └── lotte_promos_20260516_103000.json
└── superindo/
    ├── state.json
    └── superindo_promos_20260516_103500.json
```
