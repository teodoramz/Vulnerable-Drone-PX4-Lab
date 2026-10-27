#!/usr/bin/env bash
# Build the drone-lab.tar.gz archive that Ansible ships to the target.
# Run from the repo root: ./ansible/build-archive.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$REPO_ROOT/ansible/roles/drone_lab/files/drone-lab.tar.gz"

# files/ is gitignored and absent on a fresh clone.
mkdir -p "$(dirname "$DEST")"

echo "Building archive from $REPO_ROOT ..."

# Reproducible: same tree gives a byte-identical archive, so unarchive stays idempotent.
tar czf "$DEST" \
    --sort=name \
    --mtime='@0' \
    --owner=0 --group=0 --numeric-owner \
    --transform='s,^\./,drone-lab/,' \
    -C "$REPO_ROOT" \
    --exclude='.git' \
    --exclude='.venv-*' \
    --exclude='__pycache__' \
    --exclude='.playwright-mcp' \
    --exclude='.pytest_cache' \
    --exclude='node_modules' \
    --exclude='ansible' \
    `# Anchored excludes: positional in GNU tar, so they must follow the name patterns.` \
    --anchored \
    --no-wildcards-match-slash \
    --exclude='./*.png' \
    --exclude='./captures' \
    --exclude='./assets/airport-source.jpg' \
    --exclude='./services/frontend/dist' \
    .

SIZE=$(du -h "$DEST" | cut -f1)
echo "Archive: $DEST ($SIZE)"
