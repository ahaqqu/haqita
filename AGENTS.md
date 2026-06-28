# Project agent memory

This file is the project's committed home for project-intrinsic agent knowledge: build, test, release, architecture, and sharp-edge notes that should travel with the code.

## Workflow conventions

- **Worktrees**: All implementation work uses treehouse worktrees (`treehouse get`, `treehouse return`)
- **Branching**: Work happens in a branch, never on the default branch
- **Delivery**: Changes ship via PR through the no-mistakes pipeline (review → test → lint → push → CI)
- **Pipeline stages** (in order):
  1. Scrape (`--stage scrape`) — download brochure images from stores
  2. OCR (`--stage ocr`) — extract product data from images
  3. Consolidate (`--stage consolidate`) — merge and deduplicate product records
  4. Publish HTML (`--stage publish-html`) — generate static JSON/HTML output
  5. Deploy + Sync (`--stage deploy`) — deploy API to Cloudflare Pages, then sync data to deployed API
- Use `python scripts/orchestrator.py --full` to run all stages end-to-end.
- **Database repo**: Pipeline data resides in `ahaqqu/haqita-database`, linked via symlink at `database/` → `../haqita-database`. The orchestrator auto-commits and pushes to the database repo after each successful consolidation stage. To set up a fresh clone, run `bash scripts/setup_database_repo.sh`.
