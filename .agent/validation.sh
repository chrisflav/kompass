#!/usr/bin/env bash

set -euo pipefail

# Verify the worktree is clean
if ! [ -z "$(git status --porcelain)" ]; then
  echo "The working tree is not clean. Commit changes or discard if temporary."
  exit 1
fi

# Run formatting
pre-commit run --all-files

# Run tests
make test quiet=true
