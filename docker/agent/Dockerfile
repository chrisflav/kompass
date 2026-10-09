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
#   gettext                     `makemessages` (xgettext) and `compilemessages` (msgfmt), both
#                               of which .agent/validation.sh runs unconditionally
#   pandoc, texlive,            the document generators: `pdflatex` for every PDF the members and
#   texlive-fonts-extra,        finance apps produce, `pandoc` for the .docx seminar report. 22
#   texlive-latex-extra         tests in the suite shell out to these and error without them.
#
#                               `texlive-latex-extra` is here and not in the project's own
#                               images for a reason worth writing down: those are built on
#                               python:3.13-trixie, where the `texlive` metapackage already
#                               pulls it in. This one is built on a bookworm base, where it does
#                               not — and the templates need `textpos.sty`, `ltablex.sty`,
#                               `titlesec.sty` and `ragged2e.sty`, which live there. Without it
#                               `pdflatex` stops at `! LaTeX Error: File 'textpos.sty' not
#                               found.` and produces no PDF, which the tests see as
#                               TexRenderError rather than as a missing package.
#   build-essential,            what `mysqlclient` and `uwsgi` compile against: both are
#   default-libmysqlclient-dev, source-only on PyPI, so `uv sync` cannot install the project
#   pkg-config                  without them. The project's own images get these from
#                               python:3.13-trixie; a Node base has none of them
#
# The same set the project's own images install (docker/{test,production,development}/Dockerfile),
# plus the compiler toolchain, so a check that passes here passes in CI for the same reasons.
#
# Pinned to a commit-sha tag rather than `:latest`: the base decides which agent CLI is inside,
# and a floating one would change that under us. It is a tag rather than an `@sha256:` digest,
# so it is mutable in principle — immutability would be a digest, at the cost of a line nobody
# can read. To move it, pick a tag the orchestra repository's `Agent image` workflow published.
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
      texlive-latex-extra \
      build-essential \
      default-libmysqlclient-dev \
      pkg-config \
 && rm -rf /var/lib/apt/lists/*

USER agent
