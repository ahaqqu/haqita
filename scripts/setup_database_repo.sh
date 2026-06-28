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

SYMLINK_TARGET="../haqita-database"

# Handle pre-existing database/ path gracefully
if [ -L "database" ]; then
    target="$(readlink "database")"
    if [ "$target" != "$SYMLINK_TARGET" ]; then
        echo "[!] database symlink points to '$target', expected '$SYMLINK_TARGET'"
        echo "    Remove it first: rm -f database"
        exit 1
    fi
    echo "[*] database symlink already points to $SYMLINK_TARGET"
elif [ -e "database" ]; then
    echo "[!] database/ exists and is not a symlink."
    echo "    Back up your data, remove it with 'rm -rf database', then re-run this script."
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

# Create symlink only if it doesn't exist yet
if [ ! -L "database" ] && [ ! -e "database" ]; then
    ln -s "$SYMLINK_TARGET" database
    echo "[*] Symlink created: database -> $SYMLINK_TARGET"
    echo ""
    echo "Run 'git add database' to track the symlink."
fi

echo ""
echo "Setup complete."
