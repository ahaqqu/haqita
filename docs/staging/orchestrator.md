# Pipeline Orchestrator

Chains scrape → OCR → consolidation stages with JSON-based inter-stage communication.

## Overview

The orchestrator (`scripts/orchestrator.py`) is invoked when you select **[1] Run full pipeline** from `haqita.bat`. It manages the full pipeline flow:

1. **Stage 1** — Scrape all stores
2. **Stage 2** — OCR only stores with new images (saves API quota)
3. **Stage 3** — Consolidation (always runs)

## Full Pipeline Submenu

Selecting **[1]** from the main menu opens a submenu:

| Choice | Mode | Description |
|---|---|---|
| **1** | Verbose | Full run with detailed log in `output/logs/` |
| **2** | Non-verbose | Normal run (writes to database, no detailed log) |
| **3** | Dry-run + verbose | Preview all stages, no database changes, detailed log |
| **4** | Resume | Continue from last failed stage, skip completed stages |

## Resume

If a stage fails during a full pipeline run:

1. Fix the issue (e.g., restart Ollama, check API key)
2. Select **[1] → [5] Resume** from the main menu
3. The orchestrator reads `database/stage_results/` status files and skips already-completed stages
4. Pipeline continues from the first incomplete stage

No need to rerun stages one by one manually.

## Stage Communication

Each stage writes its result to `database/stage_results/` as JSON. The next stage reads this to decide what to do.

### scrape_status.json

```json
{
  "stage": "scrape",
  "timestamp": "2026-05-16T10:30:00",
  "stores": {
    "lotte": { "status": "new_images", "new_count": 3 },
    "superindo": { "status": "no_new", "new_count": 0 }
  },
  "total_new": 3
}
```

### ocr_status.json

```json
{
  "stage": "ocr",
  "timestamp": "2026-05-16T10:45:00",
  "stores": {
    "lotte": { "status": "complete", "products_extracted": 45 },
    "superindo": { "status": "skipped", "reason": "no_new_images" }
  },
  "total_products": 45
}
```

### consolidate_status.json

```json
{
  "stage": "consolidate",
  "timestamp": "2026-05-16T10:50:00",
  "status": "complete"
}
```

## Smart OCR Skipping

The orchestrator reads `scrape_status.json` after Stage 1 and records per-store status (`new_images` / `no_new` / `complete` / `skipped`) in `ocr_status.json`. Actual per-image skipping is handled by OCR's own state file (`database/ocr/<store>/state.json`), which tracks filenames already processed — so the orchestrator always invokes the OCR script for every requested store, and OCR itself decides what to re-process.

## Logging

### Console Output

Each stage's stdout is printed to the console in real-time, prefixed with `  ` for readability.

### Log Files

When running in verbose mode, detailed logs are written to:

| File | Contents |
|---|---|
| `output/logs/orchestrator_<timestamp>.log` | Orchestrator stage transitions, subprocess results |
| `output/logs/consolidate_<timestamp>.log` | Detailed match results, gate rejections, review items |

### Verbose Log Contents

The consolidation verbose log includes:

- **Matched pairs**: product names, match method, confidence
- **Lotte only / Superindo only**: unmatched products per store
- **Review queue**: items flagged for manual inspection with reason
- **Gate rejections**: which gate filtered each pair and why:
  ```
  REJECTED [gate0_unit_type] ProductA (Lotte) vs ProductB (Superindo): incompatible units 'g' vs 'pcs'
  REJECTED [gate1_brand] ProductA (Lotte) vs ProductB (Superindo): different brands 'X' vs 'Y'
  REJECTED [gate2_token_jaccard] ProductA (Lotte) vs ProductB (Superindo): token overlap 0.15 below threshold 0.30
  REJECTED [gate6_ai_verifier] ProductA (Lotte) vs ProductB (Superindo): ai_verifier_said_no
  ```

## Individual Stage Runs

You can also run single stages via the main menu:

- **Option [2]** → Scrape submenu (all stores, single store, or dry-run)
- **Option [3]** → OCR submenu (all stores, single store, specific image, or dry-run)
- **Option [4]** → Consolidation submenu (run or dry-run)

When running OCR standalone (Option [3]), it checks `scrape_status.json` if available to skip stores with no new images. If no status file exists, it OCRs all requested stores (idempotent — state file prevents re-processing).
