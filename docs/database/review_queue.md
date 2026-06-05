# `review_queue.json`

**Location:** `database/review_queue.json`

**Purpose:** Stores product pairs that the matching pipeline could not confidently resolve — flagged for manual inspection.

## Schema

```json
{
  "items": [
    {
      "detected_at": "2026-05-17T15:30:00",
      "reason": "price_ratio_exceeded",
      "product_a": {
        "name": "Kecap ABC",
        "brand": "ABC",
        "unit": "600 ml",
        "price": 18900,
        "store": "Lotte"
      },
      "product_b": {
        "name": "ABC Kecap Manis",
        "brand": "ABC",
        "unit": "600 ml",
        "price": 8500,
        "store": "Superindo"
      }
    }
  ]
}
```

## Fields

| Field | Type | Purpose |
|---|---|---|
| `detected_at` | string | ISO timestamp when the pair was flagged |
| `reason` | string | Why it was flagged (e.g., "price_ratio_exceeded", "ai_ambiguous") |
| `product_a` | object | First product in the pair (always Lotte) |
| `product_b` | object | Second product in the pair (always Superindo) |

## When Items Are Added

Items are queued when the matching pipeline encounters uncertainty:

| Gate | Condition | Reason |
|---|---|---|
| Gate 5 (Price Check) | Per-unit price ratio exceeds `price_ratio_max` (default 3.0x) | `price_ratio_too_high` |
| Gate 6 (AI Verifier) | LLM returns "NO" for an ambiguous pair | `ai_verifier_said_no` |
| Gate 6 (AI Verifier) | LLM returns an unexpected / unparseable response | `ai_verifier_unexpected` |

Other gates (0–2) record rejections in the verbose log only — they do not enqueue to `review_queue.json`.

## Behavior

- **FIFO with cap**: Max 100 items (configurable via `monitoring.review_queue_max`). Oldest items are dropped when the limit is reached.
- **Append each run**: New flagged items are appended to the existing list.
- **No auto-cleanup**: Items stay until manually reviewed or pushed out by the cap.
- **Stats link**: `active_promo.json` includes `stats.flagged_for_review` count from this file.

## Written By

Stage 3 (`consolidate.py`) — review queue section in `consolidate()`.

## Read By

Stage 4 (`publish_html.py`) — counts flagged items for `stats.flagged_for_review` in `active_promo.json`.
