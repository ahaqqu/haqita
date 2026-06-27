# Database Repo Split Plan

## Extract `database/` into Separate `haqita-database` Repo

**Status:** Plan (ready for implementation)  
**Target repo:** https://github.com/ahaqqu/haqita-database (exists, has 1 commit with skeleton README)  
**Main repo:** https://github.com/ahaqqu/haqita  
**Symlink target:** `../haqita-database` (sibling directory)

---

## Table of Contents

1. [Current State](#1-current-state)
2. [Target State](#2-target-state)
3. [Decision Record](#3-decision-record)
4. [Files to Modify](#4-files-to-modify)
5. [New Files to Create](#5-new-files-to-create)
6. [Implementation Steps](#6-implementation-steps)
7. [Auto-Commit Details](#7-auto-commit-details)
8. [Edge Cases & Risks](#8-edge-cases--risks)
9. [Verification Checklist](#9-verification-checklist)
10. [Rollback Plan](#10-rollback-plan)

---

## 1. Current State

### Main repo: `ahaqqu/haqita`

The `database/` folder is a real directory inside the main repo. All its contents are gitignored (except `.gitkeep`).

```
haqita/
├── database/                          ← real directory
│   ├── .gitkeep                       ← the only tracked file
│   ├── price_history.json             ← gitignored
│   ├── price_history.json.backup      ← gitignored
│   ├── product_catalog.json           ← gitignored
│   ├── review_queue.json              ← gitignored
│   ├── scrape/                        ← gitignored (images + state.json per store)
│   └── ocr/                           ← gitignored (OCR results + state.json per store)
├── scripts/
│   ├── orchestrator.py               ← `DATABASE_DIR = ROOT / "database"`
│   ├── consolidate.py                 ← reads/writes `database/`
│   ├── publish_html.py                ← reads `database/`
│   ├── seed_d1.py                     ← reads `database/`
│   ├── sync_cloudflare.py             ← reads `database/`, uploads images from `database/scrape/`
│   └── scrapers/ + ocr/              ← write to `database/scrape/`, `database/ocr/`
├── tests/
│   └── ...                            ← some test fixtures reference `database/scrape/` paths
├── web/
│   └── ...                            ← output JSON may contain `database/scrape/` path strings
└── docs/                              ← docs reference `database/` paths
```

### Current `.gitignore` (relevant section):

```gitignore
database/scrape/
database/ocr/
database/price_history.json
database/price_history.json.backup
database/product_catalog.json
database/review_queue.json
```

### External repo: `ahaqqu/haqita-database`

Exists on GitHub with a single commit containing a skeleton `README.md`. No data yet.

---

## 2. Target State

```
haqita/ (main repo)
├── database/ ──symlink──▶ ../haqita-database/  ← tracked symlink in git

haqita-database/ (separate git repo, sibling directory)
├── README.md
├── price_history.json
├── price_history.json.backup
├── product_catalog.json
├── review_queue.json
├── sync_state.json                      ← created by sync_cloudflare.py
├── scrape/
│   ├── lotte/
│   │   ├── state.json
│   │   └── YYYYMMDD/*.jpg
│   └── superindo/
│       ├── state.json
│       └── YYYYMMDD/*.jpg
└── ocr/
    ├── lotte/
    │   ├── state.json
    │   └── lotte_promos_*.json
    └── superindo/
        ├── state.json
        └── superindo_promos_*.json
```

**Key properties:**
- `ROOT / "database"` in Python resolves transparently through the symlink — all scripts work without code changes.
- The symlink itself is tracked in git (committed to the main repo as a symlink blob).
- No `database/` entries remain in `.gitignore` — the symlink replaces the directory.
- After each consolidation stage, the orchestrator auto-commits changes to `haqita-database`.

---

## 3. Decision Record

These decisions were made in a `grill-with-docs` session:

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 1 | Repo linking strategy | **Symlink at `database/` → `../haqita-database`** | Zero code changes to path references; transparent to all Python code. Symlink tracked in git so new clones get it automatically. |
| 2 | Tracking scope | **Everything** (JSON files, images, OCR results, state files) | The separate repo serves as the full data source of truth. |
| 3 | Pipeline sync | **Auto-commit after consolidation** (Stage 3) | Pipeline always generates fresh data; auto-commit keeps the data repo current. Runs inside `orchestrator.py` after successful consolidation. |
| 4 | Local folder | **Remove from main repo → replace with symlink** | `git rm --cached database/` removes it from the index. Symlink takes its place. |
| 5 | Config method | **No env var** | Symlink resolution handles discovery automatically. Setup instructions go in README only. |

Non-decisions (things intentionally not changed):
- No changes to `DATABASE_DIR = ROOT / "database"` in Python scripts — the symlink makes this transparent.
- No changes to data schemas or pipeline stage logic.
- No changes to Cloudflare deploy/sync — it reads/writes through the same symlink.
- Test fixtures that reference `database/scrape/` as string values are left alone (they're data content, not filesystem accesses).

---

## 4. Files to Modify

### 4.1 `.gitignore`

**Action:** Remove all `database/` entries.

Old content (lines 15-23):
```gitignore
# Database images are tracked by state, exclude large binaries
database/scrape/
database/ocr/

# Generated database files (regenerated by pipeline)
database/price_history.json
database/price_history.json.backup
database/product_catalog.json
database/review_queue.json
```

New content: delete these lines entirely. The symlink at `database/` will be tracked by git, not ignored.

**Why:** The database directory is now a git-tracked symlink to an external repo. We want the symlink committed. No gitignore entries are needed since the symlink itself is a small file, and the external repo has its own `.gitignore`.

### 4.2 `scripts/orchestrator.py`

**Action:** Add auto-commit logic after the consolidation stage.

**Where to add:**

Approach A (simpler) — inline after the consolidation call in `main()`:

In the `--full` path (non-resume), after line 430 (`cons_result = run_consolidate(...)`), add a conditional commit. Only when `--full` (not `--stage consolidate` standalone), and only on success, and only when not `--dry-run`.

In the `--full --resume` path, similarly after line 398.

Approach B (cleaner) — add a dedicated function `commit_database()` in orchestrator.py, called after consolidation.

**Function implementation:**

```python
def commit_database(logger: logging.Logger) -> None:
    """Auto-commit pipeline data to haqita-database repo.
    
    Runs git add + commit + push on the database repo linked via
    the database/ symlink. Only commits if there are changes.
    Fails gracefully (logs warning) if the repo is not set up.
    """
    db_path = (ROOT / "database").resolve()
    git_dir = db_path / ".git"
    
    if not git_dir.exists():
        logger.warning("haqita-database repo not found at %s. Skipping auto-commit.", db_path)
        return
    
    try:
        # Stage all changes
        subprocess.run(
            ["git", "-C", str(db_path), "add", "-A"],
            check=True, capture_output=True, text=True,
        )
        
        # Check if there are staged changes
        result = subprocess.run(
            ["git", "-C", str(db_path), "diff", "--staged", "--quiet"],
            capture_output=True,
        )
        if result.returncode == 0:
            logger.info("No changes to commit to haqita-database.")
            return
        
        # Commit
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        subprocess.run(
            ["git", "-C", str(db_path), "commit", "-m", f"pipeline run {timestamp}"],
            check=True, capture_output=True, text=True,
        )
        logger.info("Committed pipeline data to haqita-database.")
        
        # Push (non-blocking — warn on failure)
        push_result = subprocess.run(
            ["git", "-C", str(db_path), "push"],
            capture_output=True, text=True,
        )
        if push_result.returncode != 0:
            logger.warning("Failed to push haqita-database: %s", push_result.stderr.strip())
        else:
            logger.info("Pushed haqita-database.")
    except subprocess.CalledProcessError as e:
        logger.warning("Auto-commit to haqita-database failed: %s", e.stderr.strip()[:200])
        # Don't fail the pipeline — this is a side effect
```

**Call sites:**
- After `cons_result = run_consolidate(args.dry_run, logger)` in the `--full` path (around line 430)
- After `cons_result = run_consolidate(args.dry_run, logger)` in the `--full --resume` path (around line 398)
- Both call sites should be guarded with `if not args.dry_run and cons_result.get("status") != "error"`

**Import to add to orchestrator.py:**

```
from datetime import datetime
```
(datetime is already imported at line 32)

### 4.3 `README.md`

**Action:** Add setup instructions and update project tree.

Changes needed:
1. In the "Project Structure" section (around line 188), change the `database/` entry to indicate it's a symlink.
2. Add a new "Setup" section (before "Usage" or after "Project Structure") with:

```markdown
## Setup

### Database repo

Pipeline data lives in a separate repository: [ahaqqu/haqita-database](https://github.com/ahaqqu/haqita-database).

Clone it as a sibling of the main repo and the setup script will create the symlink:

```bash
# Clone the database repo (as a sibling directory)
git clone git@github.com:ahaqqu/haqita-database.git ../haqita-database

# Or use the setup script (does the same thing):
bash scripts/setup_database_repo.sh
```

The symlink at `database/` points to `../haqita-database/`. All pipeline scripts write through the symlink transparently. The database repo is auto-committed after each pipeline run.
```

### 4.4 `AGENTS.md`

**Action:** Add workflow convention.

Add to the "Workflow conventions" section:

```markdown
- **Database repo**: Pipeline data resides in `ahaqqu/haqita-database`, linked via symlink at `database/` → `../haqita-database`. The orchestrator auto-commits and pushes to the database repo after each successful consolidation stage. To set up a fresh clone, run `bash scripts/setup_database_repo.sh`.
```

### 4.5 `haqita-database/.gitignore`

**Action:** Add `.gitignore` to the database repo to exclude anything that shouldn't be tracked.

Suggested content:
```gitignore
# backup files
*.backup

# temp files
*.tmp
```

Note: This is in the **database repo**, not the main repo. The plan must include switching to that repo to create this file.

### 4.6 `haqita-database/README.md`

**Action:** Update the skeleton README.

```markdown
# haqita-database

Pipeline data store for [haqita](https://github.com/ahaqqu/haqita).

This repo contains all scraped brochure images, OCR results, and generated
product data (price history, product catalog, review queue, sync state).

## Updating

Data is auto-committed by the main pipeline orchestrator after each successful
consolidation stage. Do not manually edit files in this repo unless you are
fixing or enriching data — changes will be overwritten on the next pipeline run.
```

---

## 5. New Files to Create

### 5.1 `scripts/setup_database_repo.sh`

**Path:** `haqita/scripts/setup_database_repo.sh`

**Purpose:** Clone the database repo and create the symlink.

```bash
#!/usr/bin/env bash
# Setup haqita-database as a sibling clone with a symlink at database/.
#
# Usage:
#   bash scripts/setup_database_repo.sh
#
# Prerequisites:
#   - git
#   - SSH access to github.com (or HTTPS fallback)

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo ".")"
cd "$REPO_ROOT"

echo "[*] Setting up haqita-database..."

# Check if database/ already exists
if [ -e "database" ] || [ -L "database" ]; then
    echo "[!] database/ already exists. Remove it first: rm -rf database"
    echo "    (Back up any uncommitted data first!)"
    exit 1
fi

# Clone database repo as sibling
if [ -d "../haqita-database/.git" ]; then
    echo "[*] haqita-database already cloned at ../haqita-database"
else
    echo "[*] Cloning haqita-database..."
    git clone git@github.com:ahaqqu/haqita-database.git ../haqita-database
    # Fallback to HTTPS if SSH fails
    if [ $? -ne 0 ]; then
        echo "[*] SSH failed, trying HTTPS..."
        git clone https://github.com/ahaqqu/haqita-database.git ../haqita-database
    fi
fi

# Create symlink
ln -s ../haqita-database database
echo "[*] Symlink created: database -> ../haqita-database"
echo ""
echo "Setup complete. Run 'git add database' to track the symlink."
```

### 5.2 `scripts/seed_database_repo.py` (optional, one-time use)

**Path:** `haqita/scripts/seed_database_repo.py`

**Purpose:** Copy current `database/` contents into the fresh `haqita-database` clone and push the initial commit. One-time script — delete after use.

```python
"""
One-time seed: copy current database/ contents into haqita-database repo and push.

Usage:
    python scripts/seed_database_repo.py

Prerequisites:
    - haqita-database cloned at ../haqita-database
    - Symlink at database/ -> ../haqita-database
    - Current database/ directory still has real files (before symlink swap)
"""
```

Detailed logic:
1. Copy all files from `haqita/database/` (the real dir) into `haqita-database/`
2. Create initial `.gitignore` in haqita-database
3. `git -C ../haqita-database add -A`
4. `git -C ../haqita-database commit -m "initial seed from pipeline"`
5. `git -C ../haqita-database push`

---

## 6. Implementation Steps

> **⚠️ CRITICAL: Data preservation warning**
> 
> Steps 7 and 8 below involve deleting the real `database/` directory and replacing it with a symlink.
> **All data inside `database/` (pipeline JSON files, images, OCR results) will be permanently lost
> if the seed step (Step 7) is not completed correctly first.**
> 
> **Safeguard procedure before Step 7:**
> 1. Verify `../haqita-database` exists and is a valid git repo: `ls ../haqita-database/.git`
> 2. Verify the seed copy was successful: `ls ../haqita-database/price_history.json`
> 3. Verify the data looks correct: `python -c "import json; d=json.load(open('../haqita-database/price_history.json')); print(len(d.get('snapshots',[])), 'snapshots')"`
> 4. Only then proceed to delete the real `database/` directory.
> 
> **After Step 8 (symlink created):**
> - Immediately verify data is accessible through the symlink: `ls database/price_history.json`
> - If the symlink is broken or the directory is empty, **do NOT commit**. Restore from backup: `rm database/ && git checkout HEAD -- database/` to recover the real directory.

The implementation should be done in this exact order:

### Step 1: Verify prerequisites

```bash
# Confirm haqita-database repo exists and is accessible
git ls-remote https://github.com/ahaqqu/haqita-database.git

# Confirm current state
cd /home/angga/projects/firstmate/projects/haqita
git status
ls -la database/
```

### Step 2: Create `scripts/setup_database_repo.sh`

Write the new file per section 5.1 above.

### Step 3: Modify `.gitignore`

Remove lines 15-23 (all `database/` entries). Keep the rest of the file intact.

### Step 4: Modify `scripts/orchestrator.py`

Add the `commit_database()` function and two call sites per section 4.2.

### Step 5: Update `README.md`

Add setup instructions, update project tree.

### Step 6: Update `AGENTS.md`

Add database repo convention.

### Step 7: Seed `haqita-database` with current data

> **⚠️ DATA BACKUP — do this before deleting the real directory**

```bash
# 1. Ensure haqita-database is cloned
git clone git@github.com:ahaqqu/haqita-database.git ../haqita-database

# 2. Copy all current database/ files into the clone
cp -a database/* ../haqita-database/
cp database/.gitkeep ../haqita-database/ 2>/dev/null || true

# 3. Add .gitignore to the database repo
cat > ../haqita-database/.gitignore << 'EOF'
*.backup
*.tmp
EOF

# 4. Verify the seed — do NOT proceed if this fails
ls ../haqita-database/price_history.json  || { echo "MISSING price_history.json"; exit 1; }
ls ../haqita-database/product_catalog.json || { echo "MISSING product_catalog.json"; exit 1; }
ls ../haqita-database/scrape/lotte/state.json || echo "WARNING: scrape dir not fully seeded"
ls ../haqita-database/ocr/lotte/state.json || echo "WARNING: ocr dir not fully seeded"

# 5. Commit and push
cd ../haqita-database
git add -A
git commit -m "initial seed from pipeline"
git push
```

> **Before proceeding to Step 8:** verify the push was successful by checking the remote repo
> at https://github.com/ahaqqu/haqita-database. All data files should be visible there.

### Step 8: Swap symlink in main repo

> **⚠️ This is the destructive step. Data preservation checklist BEFORE running:**
> 
> - [ ] `../haqita-database/price_history.json` exists and has data
> - [ ] `../haqita-database/product_catalog.json` exists and has data
> - [ ] `../haqita-database/scrape/` has the image directories
> - [ ] `../haqita-database/ocr/` has the OCR result files
> - [ ] The seed commit was pushed to GitHub successfully
> - [ ] `cd ../haqita-database && git log --oneline -1` shows the seed commit
> - [ ] `git -C ../haqita-database status --porcelain` is clean (no uncommitted changes)
> - [ ] Make a full backup: `cp -a database /tmp/database-backup-$(date +%Y%m%d)`

```bash
# 1. Remove database/ from git index (keeps files on disk)
cd /home/angga/projects/firstmate/projects/haqita
git rm -r --cached database/

# 2. Remove the real database/ directory
rm -rf database/

# 3. Create the symlink
ln -s ../haqita-database database

# 4. IMMEDIATELY verify the symlink works — data should be accessible
ls database/price_history.json         # must show the file
ls database/scrape/lotte/              # must show image dirs or state.json

# 5. If verification fails, RESTORE IMMEDIATELY:
#    rm database/ && git checkout HEAD -- database/

# 6. Track the symlink in git
git add database

# 7. Commit
git commit -m "replace database/ dir with symlink to haqita-database repo"
```

> After the commit, run `git log --oneline -1` to confirm the commit exists.
> If anything went wrong, use `git reset --soft HEAD~1` to undo the commit
> and restore the real directory from `/tmp/database-backup-*`.

### Step 9: Final verification

Run verification checks per section 9 below.

### Step 10: Update `haqita-database/README.md`

Switch to the database repo and update its README per section 4.6.

---

## 7. Auto-Commit Details

### When does it trigger?

- Only during `python scripts/orchestrator.py --full` (or `--full --resume`).
- Only after a successful consolidation stage.
- NOT triggered during individual stage runs (e.g., `--stage consolidate`).
- NOT triggered during `--dry-run`.

### What does it commit?

Everything in the database repo working tree that has changed:
- New images from scrape stage
- New OCR results from OCR stage
- Updated price_history.json, product_catalog.json, review_queue.json from consolidation
- Updated sync_state.json from deploy+sync stage

### What if there are local changes in haqita-database?

If a developer has manually edited files in haqita-database (e.g., to fix data), those changes will be included in the auto-commit. This is intentional — manual fixes should persist across pipeline runs.

### What if push fails?

The commit still happens locally. Push failure is logged as a warning but does not abort the pipeline. This handles offline development gracefully.

### What if the symlink doesn't exist?

The function detects that `.git` is missing at the resolved path and logs a warning. The pipeline continues without committing. This handles the case where a developer hasn't set up the database repo yet.

### Commit message format

```
pipeline run YYYYMMDD_HHMMSS
```

Example:
```
pipeline run 20260628_142301
```

---

## 8. Edge Cases & Risks

### 8.1 Symlink broken after clone

**Risk:** Someone clones the main repo, gets the symlink, but `../haqita-database` doesn't exist. Scripts that write to `ROOT / "database"` will fail with `FileNotFoundError`.

**Mitigation:** 
- The setup script catches this early and guides the user.
- The auto-commit function logs a clear warning.
- README has explicit setup instructions.

### 8.2 Windows compatibility

**Risk:** Windows requires either Developer Mode (for symlink creation) or admin privileges. The `ln -s` command in the setup script won't work on standard Windows.

**Mitigation:** 
- Document that Windows users need Developer Mode enabled or should use WSL.
- The setup script could check `uname` and provide platform-specific guidance.

### 8.3 Large images in git history

**Risk:** Images in `database/scrape/` are binary files up to several MB each. Over time, git history in haqita-database could grow large.

**Mitigation:** This is acceptable since the repo is data-only. If it becomes a problem, consider:
- Git LFS for image files
- Periodic history cleanup
- Moving images to R2-only storage with state tracking

### 8.4 Concurrent pipeline runs

**Risk:** If two pipeline runs happen concurrently, the auto-commit could conflict.

**Mitigation:** The orchestrator runs sequentially by design (one stage at a time). Concurrent runs are not supported. The `--resume` flag uses stage status files to coordinate.

### 8.5 Stale `database/` directory after pulling

**Risk:** An existing clone of the main repo has a real `database/` directory from before the split. After `git pull`, they get the symlink in the index but still have the old directory.

**Mitigation:** The setup script checks if `database/` exists and refuses to overwrite. Instructions in README tell the user to `rm -rf database/` first (after making sure they don't need the local data). Alternatively, they can just keep using their real directory — it'll work the same way.

### 8.6 The `.gitkeep` file

**Risk:** The old `database/.gitkeep` was the only tracked file. After the split, we don't need it in the main repo.

**Mitigation:** `git rm --cached database/.gitkeep` is part of `git rm -r --cached database/`. If we want to keep a placeholder, the symlink itself serves that purpose.

### 8.7 Orphaned `agentic_engineering/clean_dummy_data.py`

**Risk:** This script references `database/` paths for cleanup. It still works since it goes through the symlink. No changes needed.

### 8.8 `web/public/active_promo.json` contains `database/scrape/` path strings

**Risk:** These are data content strings (image_path values), not filesystem references. They travel with the data and are correct by value. No changes needed.

---

## 9. Verification Checklist

Run these checks after implementation:

### 9.1 Symlink integrity

```bash
# Symlink exists and resolves
ls -la database/
# Expected: database -> ../haqita-database

# Symlink is tracked in git
git ls-files database
# Expected: database (not database/ or database/*)
```

### 9.2 Gitignore is clean

```bash
# No database/ entries remain
grep -n "database/" .gitignore
# Expected: no output
```

### 9.3 Pipeline still works

```bash
# Dry-run the pipeline
python scripts/orchestrator.py --full --dry-run --verbose

# Run a single stage that reads from database/
python scripts/consolidate.py --dry-run

# Run publish
python scripts/publish_html.py --dry-run
```

### 9.4 All scripts can find database/

```bash
# Check that Python resolves through symlink
python -c "from pathlib import Path; p = Path('database').resolve(); print(p); print(p.exists())"
# Expected: /path/to/haqita-database  True
```

### 9.5 Tests pass

```bash
pytest tests/ -v
```

### 9.6 Setup script works from a fresh clone simulation

```bash
# Create a temp directory to test the setup flow
mkdir -p /tmp/test-setup
cd /tmp/test-setup
git clone git@github.com:ahaqqu/haqita.git
cd haqita
git checkout <branch-with-changes>
bash scripts/setup_database_repo.sh
ls -la database/
# Expected: database -> ../haqita-database
```

### 9.7 Auto-commit works

```bash
# Run the full pipeline (or up to consolidate)
python scripts/orchestrator.py --stage scrape
python scripts/orchestrator.py --stage ocr
python scripts/orchestrator.py --full --stage consolidate

# Check that the database repo has a new commit
git -C ../haqita-database log --oneline -3
```

### 9.8 Database repo push works

```bash
# Confirm the auto-commit pushed
git -C ../haqita-database log --oneline -1
# Check remote
git -C ../haqita-database remote -v
```

---

## 10. Rollback Plan

If something goes wrong, revert the changes:

### Option A: Full rollback

```bash
# Revert the main repo commits
git revert HEAD --no-edit   # reverts the symlink commit
# OR
git reset --hard HEAD~2     # if no other commits happened

# Restore .gitignore from git
git checkout HEAD~1 -- .gitignore

# Remove symlink, restore real directory
rm database/
git checkout HEAD~1 -- database/
```

### Option B: Keep symlink, revert auto-commit

```bash
# Revert only the orchestrator changes
git revert <commit-that-added-auto-commit>
```

### Option C: Restore haqita-database to pre-seed state

```bash
# In the database repo
cd ../haqita-database
git reset --hard HEAD~1   # removes the initial seed commit
git push --force
```

---

## Appendix A: Full Diff of Changes

### `.gitignore`

```diff
- # Database images are tracked by state, exclude large binaries
- database/scrape/
- database/ocr/
- 
- # Generated database files (regenerated by pipeline)
- database/price_history.json
- database/price_history.json.backup
- database/product_catalog.json
- database/review_queue.json
```

### `scripts/orchestrator.py`

```diff
+ from datetime import datetime  (already present at line 32)
+
+ def commit_database(logger):
+     """Auto-commit pipeline data to haqita-database repo."""
+     db_path = (ROOT / "database").resolve()
+     git_dir = db_path / ".git"
+     if not git_dir.exists():
+         logger.warning("haqita-database repo not found at %s. Skipping auto-commit.", db_path)
+         return
+     try:
+         subprocess.run(["git", "-C", str(db_path), "add", "-A"], check=True, capture_output=True, text=True)
+         result = subprocess.run(["git", "-C", str(db_path), "diff", "--staged", "--quiet"], capture_output=True)
+         if result.returncode == 0:
+             logger.info("No changes to commit to haqita-database.")
+             return
+         timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
+         subprocess.run(["git", "-C", str(db_path), "commit", "-m", f"pipeline run {timestamp}"],
+                        check=True, capture_output=True, text=True)
+         logger.info("Committed pipeline data to haqita-database.")
+         push_result = subprocess.run(["git", "-C", str(db_path), "push"], capture_output=True, text=True)
+         if push_result.returncode != 0:
+             logger.warning("Failed to push haqita-database: %s", push_result.stderr.strip())
+         else:
+             logger.info("Pushed haqita-database.")
+     except subprocess.CalledProcessError as e:
+         logger.warning("Auto-commit to haqita-database failed: %s", e.stderr.strip()[:200])

After line 430 (cons_result = run_consolidate(...) in --full path):
+         if not args.dry_run and cons_result.get("status") != "error":
+             commit_database(logger)

After line 398 (same in --resume path):
+         if not args.dry_run and cons_result.get("status") != "error":
+             commit_database(logger)
```

### `README.md`

Add new "Setup" section with clone + symlink instructions. Update project tree to show `database/` as symlink.

### `AGENTS.md`

Add database repo convention line.

---

## Appendix B: Key Files Referenced

| File in main repo | Purpose | Change needed? |
|---|---|---|
| `.gitignore` | Exclude files from git | Yes — remove database/ entries |
| `scripts/orchestrator.py` | Pipeline orchestrator | Yes — add commit_database() |
| `scripts/setup_database_repo.sh` | Setup script | New file |
| `README.md` | Project documentation | Yes — add setup instructions |
| `AGENTS.md` | Agent conventions | Yes — add db repo convention |
| `scripts/consolidate.py` | Consolidation stage | No — path resolution through symlink |
| `scripts/publish_html.py` | HTML output stage | No — path resolution through symlink |
| `scripts/seed_d1.py` | D1 seed script | No — path resolution through symlink |
| `scripts/sync_cloudflare.py` | Cloudflare sync | No — path resolution through symlink |
| `scripts/scrapers/base_scraper.py` | Base scraper | No — path resolution through symlink |
| `scripts/ocr/run_ocr.py` | OCR runner | No — path resolution through symlink |
| `web/public/active_promo.json` | Output data | No — data content, not filesystem ref |
| `agentic_engineering/clean_dummy_data.py` | Cleanup utility | No — path resolution through symlink |

| File in haqita-database repo | Purpose | Change needed? |
|---|---|---|
| `README.md` | Repo description | Yes — update skeleton |
| `.gitignore` | Exclude backups/temps | New file |
