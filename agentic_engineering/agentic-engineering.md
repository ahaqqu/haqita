# Agentic Engineering: Haqita Dummy Pipeline

Run the full haqita pipeline against isolated dummy fixtures in a temp workspace, with production-safe dummy writes to D1/R2.

## Objectives

1. **Auto self-fix end-to-end scenarios** — Run the dummy pipeline, detect failures via script assertions, fix them, and rerun until all checks pass.
2. **Auto self-update README.md** — After a successful dummy run, update `README.md` with any new setup instructions or failure patterns discovered.
3. **Auto self-suggest agentic-engineering improvements** — Propose simpler or more robust ways to run, verify, or isolate the dummy pipeline.
4. **self-improve troubleshoot** — Detect new failure modes, log them, and incorporate fixes into the scripts automatically.

## 3-step flow

```bash
# Step 1 — Install deps, verify .env, gate on unit tests
bash agentic_engineering/prepare.sh

# Step 2 — Run the full pipeline (interactive or batch)
./haqita.sh                # interactive menu
HAQITA_BATCH=1 ./haqita.sh # non-interactive batch mode

# Step 3 — Verify end results in an isolated workspace, sync dummy data,
#          assert Cloudflare tabs, capture screenshots
bash agentic_engineering/verify.sh
```

- `agentic_engineering/prepare.sh` creates the venv, installs `requirements.txt`, checks `GEMINI_API_KEY`, and runs `pytest tests/matching/ -v` as a gate.
- `agentic_engineering/verify.sh` creates `/tmp/haqita_verify_*`, starts `agentic_engineering/dummy_server.py`, invokes `haqita.sh` in batch mode, runs sync_cloudflare with `DUMMY_DATA=1`, runs matching tests, verifies tab content via `?show_dummy=true`, and captures screenshots.

## Isolation strategy

- **Temp workspace**: `/tmp/haqita_verify_*` with a copy of the repo (excludes `.git`, `.venv`, `database`, `output`).
- **Dummy server**: Local HTTP server (`agentic_engineering/dummy_server.py`) served on `:18080` with dummy Lotte/Superindo promo pages.
- **Production D1/R2 writes**: Gated by `dummy_data=true`. Normal users never see dummy data; append `?show_dummy=true` to see only dummy data.
- **Mocks**: `MOCK_OCR=1` and `MOCK_AI_VERIFIER=1` avoid Gemini quota issues, using real-captured fixtures from `agentic_engineering/mocks/ocr_fixtures/`.

## Mock external APIs

```bash
MOCK_OCR=1 MOCK_AI_VERIFIER=1 bash agentic_engineering/prepare.sh && HAQITA_BATCH=1 ./haqita.sh && bash agentic_engineering/verify.sh
```

## Fixture regeneration

To regenerate OCR and AI verifier fixtures from real Gemini calls:

```bash
CAPTURE_FIXTURES=1 .venv/bin/python agentic_engineering/capture_fixtures.py
```

This runs real OCR on `agentic_engineering/images/` and captures AI verifier responses for ambiguous pairs.

## Cleanup

```bash
rm -rf /tmp/haqita_verify_*
```

## Self-fix loop

1. Run `bash agentic_engineering/verify.sh` and note which assertion failed.
2. Inspect the stage status files in the workspace `output/stage_results/`.
3. Fix the root cause (pipeline script, dummy server, or fixture).
4. Re-run `bash agentic_engineering/verify.sh`.
5. Repeat up to 5 times. Escalate if unresolved.
