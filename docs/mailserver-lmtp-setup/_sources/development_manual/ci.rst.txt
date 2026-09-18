.. _development_manual/ci:

=======================
Continuous Integration
=======================

Every pull request and every commit on ``main`` is validated by a set of GitHub Actions workflows.
All checks must pass before a pull request can be merged.

Workflows
---------

Pre-commit checks
^^^^^^^^^^^^^^^^^

The ``pre-commit`` workflow runs on every pull request and every push to ``main``. It executes
all `pre-commit <https://pre-commit.com>`_ hooks on all files, which includes linting and
formatting of Python code via `ruff <https://docs.astral.sh/ruff/>`_.

Check translations
^^^^^^^^^^^^^^^^^^

The ``check-translations`` workflow runs on every pull request and every push to ``main``. It
regenerates the translation files using ``make uv translate`` and checks two things:

- The generated ``.po`` files must not differ from the committed files. If they do, the
  translation files are out of date and need to be regenerated and committed.
- No fuzzy markers may remain in any ``.po`` file.

See :ref:`development_manual/translations` for details on how to update translation files.

Build documentation
^^^^^^^^^^^^^^^^^^^

The ``build-docs`` workflow runs on every pull request and every push to ``main``. It builds
the Sphinx documentation and deploys it to GitHub Pages. For pull requests, a comment is posted
with a link to the deployed documentation preview.

Build and test
^^^^^^^^^^^^^^

The ``build-internal`` and ``build-fork`` workflows run on every pull request and every push to
``main``. They build the production Docker image and then:

- Run the full test suite.
- Enforce 100% test coverage. Any uncovered line causes the job to fail.

For pull requests, a comment is posted with the tags of the built Docker images.

See :ref:`development_manual/testing` for details on how to run the tests locally.

Deploying pull requests to a staging server
--------------------------------------------

A pull request can be deployed to a staging server by adding the ``awaiting-deployment`` label
to it. This triggers the ``deploy-pr`` workflow, which deploys the pull request to the staging
server and posts a comment with the URL of the deployed instance.
