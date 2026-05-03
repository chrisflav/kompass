#!/usr/bin/env bash

set -euo pipefail

# Verify the worktree is clean
if ! [ -z "$(git status --porcelain)" ]; then
  echo "The working tree is not clean. Commit changes or discard if temporary."
  exit 1
fi

# Run formatting
pre-commit run --all-files

# Check translation files are up to date
make uv translate
if ! [ -z "$(git diff --name-only)" ]; then
  echo "'make uv translate' reported that translation files are not up to date."
  git diff
  exit 1
fi

# Run tests
make test quiet=true
