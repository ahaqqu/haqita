# Stage 1: Scrape

Downloads current promo brochure images from supermarket websites.

## Overview

| | |
|---|---|
| **Input** | Superindo / Lotte Mart website URLs (from `config.yaml`) |
| **Output** | Brochure images in `database/scrape/<store>/<YYYYMMDD>/` (JPG/PNG) |
| **State** | `database/scrape/<store>/state.json` — MD5 tracking to skip already-seen images |
| **Dry-run** | Reports new images without downloading |

## How It Works

1. Fetch HTML from configured store URLs
2. Parse HTML to extract promo image URLs
3. Download each image, compute MD5 hash
4. Check size/dimension thresholds (skip too-small images)
5. Check against state file — skip if MD5 already seen
6. Save new images to `database/scrape/<store>/<YYYYMMDD>/`
7. Update state file with new MD5 hashes

## Image Classification

Each downloaded image is classified as:

| Status | Meaning |
|---|---|
| `[NEW]` | New image, downloaded and saved |
| `[SKIP]` | Already processed (MD5 match) |
| `[SKIP]` | Too small (below `min_image_size_kb`) |
| `[SKIP]` | Dimensions too small (below `min_dimension`) |
| `[SKIP]` | Duplicate content within same run (same MD5) |
| `[ERR]` | Download failed |

## Configuration

Store-specific settings in `config.yaml`:

```yaml
scrapers:
  lotte:
    url: https://www.lottemart.co.id/all-promo-mart
    min_image_size_kb: 50
    request_delay_seconds: 2

  superindo:
    urls:
      - https://www.superindo.co.id/promosi/katalog-super-hemat/
      - https://www.superindo.co.id/promosi/promo-koran/
    region_filter: jabodetabek-palembang
    min_image_size_kb: 50
    request_delay_seconds: 2
```

## Usage

Via `haqita.bat` → Option [2] → Scrape submenu:

| Choice | Action |
|---|---|
| **1** | Scrape all stores |
| **2** | Scrape Lotte Mart only |
| **3** | Scrape Superindo only |
| **4** | Dry-run (report new images only) |

## Output Structure

```
database/scrape/
├── lotte/
│   ├── state.json            # MD5 tracking
│   └── 20260516/             # Date-based folder
│       ├── promo_abc123.jpg
│       └── promo_def456.jpg
└── superindo/
    ├── state.json
    └── 20260516/
        ├── promo_ghi789.jpg
        └── promo_jkl012.jpg
```

## State File

`database/scrape/<store>/state.json`:

```json
{
  "last_run": "2026-05-16T10:30:00",
  "processed": [
    { "filename": "promo_abc123.jpg", "md5": "a1b2c3d4..." },
    { "filename": "promo_def456.jpg", "md5": "e5f6g7h8..." }
  ]
}
```
