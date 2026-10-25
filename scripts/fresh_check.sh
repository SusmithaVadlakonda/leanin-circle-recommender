#!/usr/bin/env bash
# Clone the committed repo into a temporary folder and follow the README there:
# make setup, make test, make smoke. This catches files that exist locally but were
# never committed, and setup steps the README forgot to mention.
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
if [ -n "$(git -C "$repo_root" status --porcelain)" ]; then
  echo "fresh-check: note that uncommitted changes are not part of this check"
fi

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT

git clone --quiet "$repo_root" "$workdir/repo"
cd "$workdir/repo"
make setup
make test
make smoke
echo "fresh-check: passed in a clean clone of commit $(git rev-parse --short HEAD)"
