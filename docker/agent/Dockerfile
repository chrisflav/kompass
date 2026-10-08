# The image an orchestra agent runs in when the task is on this repository.
#
# Named by `.agent/config.json` (`execution.image`), which orchestra's kubernetes execution
# backend reads: one pod per task, this image, the checkout copied in. The default image it
# would otherwise use is a Node and Lean toolbox — it carries the agent CLI, git, uv and little
# else, which is right for the repositories it was built for and leaves this one unable to run
# its own checks. Every task failed `.agent/validation.sh` at `pre-commit: command not found`.
#
# What is added, and who needs it:
#
#   make                        `make uv translate`, and the rest of the Makefile an agent reads
#                               as documentation for how this project is driven
#   gettext                     `makemessages` (xgettext) and `compilemessages` (msgfmt). With
#                               these present, validation checks catalogue freshness and builds
#                               the `.mo` files through Django rather than the polib fallback in
#                               .agent/compile-messages.py
#   pandoc, texlive,            the document generators: `pdflatex` for every PDF the members and
#   texlive-fonts-extra         finance apps produce, `pandoc` for the .docx seminar report. 20
#                               tests in the suite shell out to these and error without them
#   build-essential,            what the `mysql` and `server` extras compile against —
#   default-libmysqlclient-dev, mysqlclient and uwsgi are source-only on PyPI. Not needed for the
#   pkg-config                  tests, which use SQLite, but `uv sync --all-extras` is a
#                               reasonable thing for an agent to want to run
#
# The same set the project's own images install (docker/{test,production,development}/Dockerfile),
# plus the compiler toolchain, so a check that passes here passes in CI for the same reasons.
#
# Pinned by digest-bearing sha rather than `:latest`: the tag this derives from decides which
# agent CLI is inside, and a floating base would change that under us. To move it, pick a tag
# the orchestra repository's `Agent image` workflow has published and bump the line below.
FROM ghcr.io/chrisflav/orchestra-agent:e5d558539a39a62b63036c13341730f3c73d994b

# apt needs root; the base image runs as the unprivileged `agent`, and so must this one — the
# agent CLIs refuse `--dangerously-skip-permissions` under uid 0, which is how orchestra runs
# them.
USER root

# `--no-install-recommends` keeps texlive's suggested packages out; the fonts come from
# texlive-fonts-extra, which is named because the templates use them.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      make \
      gettext \
      pandoc \
      texlive \
      texlive-fonts-extra \
      build-essential \
      default-libmysqlclient-dev \
      pkg-config \
 && rm -rf /var/lib/apt/lists/*

USER agent
