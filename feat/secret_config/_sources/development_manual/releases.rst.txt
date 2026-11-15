.. _development_manual/releases:

========
Releases
========

Development happens on ``main``. A release is a version tag on a commit, and every version that
still receives fixes has a maintenance branch, so a fix can be shipped to an older version
without everything that has landed on ``main`` since.

Versions and branches
---------------------

- **Tags** are annotated and named ``vX.Y.Z``, for example ``v2.0.1``. The tag message says what
  the release contains. The version in ``pyproject.toml`` matches the tag.
- **Maintenance branches** are named ``release/X.Y`` and start from a commit on ``main``. Fixes
  for that version land there and are released as new ``vX.Y.Z`` tags on the branch.
- **Fixes go to main first.** A fix is merged into ``main`` and then *backported* into the
  release branches that need it, never the other way around, so ``main`` never lacks a fix that a
  release has.

Docker images of a release
--------------------------

Pushing a ``v*`` tag runs the :ref:`build and test <development_manual/ci>` workflow for the
tagged commit: it builds the images, runs the full test suite with the coverage check, and only
then publishes them under the tag's name:

- ``ghcr.io/chrisflav/kompass:vX.Y.Z``
- ``ghcr.io/chrisflav/kompass-nginx:vX.Y.Z``
- ``ghcr.io/chrisflav/kompass-spa:vX.Y.Z``

``latest`` and the ``main-<sha>`` tags stay with ``main``; a release tag never moves them. To run
a release, pull these images, or check out the tag and build from it.

.. important::

   GitHub runs the workflow **from the tagged commit**, not from ``main``. A release branch only
   publishes images for its tags if it already contains the workflow that does so (added in
   #355). A branch cut from an older commit needs that change backported before its first tag is
   pushed; otherwise the tag push runs nothing.

Backporting a fix
-----------------

Once the fix is merged into ``main``:

1. Create a branch off the release branch, preferably in a separate worktree so that the
   development environment keeps running on its own checkout, and cherry-pick the fix's commits:

   .. code-block:: bash

      git fetch origin
      git worktree add -b backport/<topic> ../kompass-backport origin/release/2.0
      cd ../kompass-backport
      git cherry-pick <commit>...

   Use ``git cherry-pick -x`` for commits that are not part of the fix itself (such as a CI
   change the old branch also needs), so the backported commit records where it came from.

2. Open a pull request **into the release branch** (``--base release/2.0``). The CI workflows
   run for pull requests into any branch, so the backport is tested against the old code base,
   with the same coverage and translation checks as ``main``.

3. Merge it. The repository only allows squash merges, so the backport lands as one commit:
   name each of its parts and where it came from in the squash message.

Cutting a release
-----------------

1. Make sure the release branch contains everything the release should, and that ``version`` in
   ``pyproject.toml`` is the version to tag.
2. Tag the head of the release branch and push the tag:

   .. code-block:: bash

      git fetch origin
      git tag -a v2.0.2 origin/release/2.0     # the editor opens for the tag message
      git push origin v2.0.2

3. Watch the "Build and Test (Internal)" run for the tag. Once it succeeds, the three images
   are on GHCR under the tag's name.

To start a new maintenance branch, push the commit on ``main`` it should start from:

.. code-block:: bash

   git push origin <commit>:refs/heads/release/X.Y
