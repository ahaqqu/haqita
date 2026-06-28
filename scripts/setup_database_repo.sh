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
    git clone git@github.com:ahaqqu/haqita-database.git ../haqita-database || {
        echo "[*] SSH failed, trying HTTPS..."
        git clone https://github.com/ahaqqu/haqita-database.git ../haqita-database
    }
fi

# Create symlink
ln -s ../haqita-database database
echo "[*] Symlink created: database -> ../haqita-database"
echo ""
echo "Setup complete. Run 'git add database' to track the symlink."
