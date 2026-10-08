#!/usr/bin/env bash
#
# What an agent's work has to pass before the task is considered done.
#
# Everything here runs on `uv` alone, in a single container with no services beside it. The
# previous version shelled out to `make`, which runs the tests through `docker compose` — four
# services, built images, a MariaDB — and an agent has no Docker socket and no capabilities to
# get one. It failed at line 12 with `pre-commit: command not found`, three retries deep, on
# every task.
#
# The tools this does need — gettext for the catalogues, pdflatex and pandoc for the documents
# the tests generate — are in docker/agent/Dockerfile, which `.agent/config.json` names as the
# image a task runs in. Nothing here guards against their absence: an image that lacks them
# cannot validate this project, and saying so by failing is better than skipping checks.
#
# `make test` is still the fuller check and still what CI runs: it exercises MySQL, memcached
# and the real cache middleware. This is the subset that can run anywhere, which is worth more
# than a check that cannot run at all.

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

# Verify the worktree is clean
if ! [ -z "$(git status --porcelain)" ]; then
  echo "The working tree is not clean. Commit changes or discard if temporary."
  exit 1
fi

# Formatting and lint. `uvx` rather than a bare `pre-commit`: it is a developer tool rather than
# a dependency of the project, so it is not in the lock file and not in the environment.
uvx --python 3.13 pre-commit run --all-files

# The catalogues Django reads at runtime. `*.mo` is gitignored and not committed, so without
# this a test asserting a German string reads the English msgid instead -- a real failure in
# `contrib`, and nothing to do with the change being validated. docker/test's entrypoint does
# the same thing before its run, for the same reason.
(cd jdav_web && uv run --python 3.13 python manage.py compilemessages --locale de -v 0)

# Whether the `.po` sources are up to date with the code.
(cd jdav_web && uv run --python 3.13 python manage.py makemessages --locale de --no-location --no-obsolete)
if ! [ -z "$(git diff --name-only)" ]; then
  echo "'makemessages' reported that translation files are not up to date."
  git diff
  exit 1
fi

# Tests, against SQLite and an in-process cache -- see .agent/config/settings.toml. The app list
# is docker/test/entrypoint-master.sh's, so the two run the same suite.
cd jdav_web
KOMPASS_CONFIG_DIR_PATH=../.agent/config \
  uv run --python 3.13 python manage.py test \
  startpage finance members contrib logindata mailer material ludwigsburgalpin feedback \
  test_data jdav_web \
  --noinput -v "${DJANGO_TEST_VERBOSITY:-1}"
