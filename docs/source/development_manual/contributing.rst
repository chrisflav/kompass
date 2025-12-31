.. _development_manual/contributing:

============
Contributing
============

Any form of contribution is appreciated. If you found a bug or have a feature request, please file an
`issue <https://github.com/chrisflav/kompass/issues>`_. If you want to help with the documentation or
want to contribute code, please open a `pull request <https://github.com/chrisflav/kompass/pulls>`_.

.. note::

    Please read this page carefully before contributing.

Organization and branches
-------------------------

The stable development happens on the ``main``-branch for which only maintainers have write access. Any pull request
should hence be targeted at ``main``. Regularly, the production instances are updated to the latest ``main`` version,
in particular these are considered to be stable.

If you have standard write access to the repository, feel free to create new branches.  To make organization
easier, please follow the branch naming convention: ``<username>/<feature>``.


Pull requests
-------------

All pull requests are squash merged into ``main``. The pull request description becomes the commit message,
so it should be clear and concise.

Title format
^^^^^^^^^^^^

Pull request titles must follow the conventional commit format:

- ``feat(scope): short description`` - New features
- ``fix(scope): short description`` - Bug fixes
- ``docs(scope): short description`` - Documentation changes
- ``chore(scope): short description`` - Maintenance tasks
- ``refactor(scope): short description`` - Code refactoring

The scope should indicate the affected component (e.g., ``members``, ``finance``, ``test``, ``ci``).

Description format
^^^^^^^^^^^^^^^^^^

Pull request descriptions should:

- Be kept short and concise
- Avoid repetitions
- Use no formatting beyond backticks for inline code (````code````) or code blocks
- Explain what changes were made and why
- Not repeat information already in the title
- Not include "Generated with Claude" or similar lines
- Use ``Co-authored-by: Name <email>`` to indicate co-authors if needed


.. _development_manual/contributing/documentation:

Documentation
-------------

If you want to contribute to the documentation, please follow the steps below.

Online (latest release version): https://chrisflav.github.io/kompass

- This documentation is build `sphinx <https://www.sphinx-doc.org/>`_ and `awsome sphinx theme <https://sphinxawesome.xyz/>`_ the source code is located in ``docs/``.
- All documentation is written in `reStructuredText <https://www.sphinx-doc.org/en/master/usage/restructuredtext/index.html>`_ and uses the `sphinx directives <https://www.sphinx-doc.org/en/master/usage/restructuredtext/directives.html>`_.
    - The directives can vary due to the theme, see the `awesome sphinx theme documentation <https://sphinxawesome.xyz/demo/notes/>`_.
- All technical documentation is written in English, user documentation is written in German.

To read the documentation build it locally and view it in your browser:

.. code-block:: bash

    cd docs/
    make html

    # MacOS (with firefox)
    open -a firefox $(pwd)/build/html/index.html
    # Linux
    firefox $(pwd)/build/html/index.html

Code
----

If you want to contribute code, please follow the inital setup steps in the :ref:`development_manual/setup` section. And dont forget to :ref:`document <development_manual/contributing/documentation>` your code properly and write tests.

Linting and formatting
^^^^^^^^^^^^^^^^^^^^^^

We use `pre-commit <https://pre-commit.com>`_ to automatically lint and format the (python) code. To locally run
``pre-commit``, install:

.. code-block:: bash

    pip install pre-commit

Then you can manually run the linters and formatters:

.. code-block:: bash

    pre-commit

This runs the suite on all staged files. If you want to run it on all files, use

.. code-block:: bash

    pre-commit run --all-files

Tests
^^^^^

Full test coverage is enforced by continuous integration, for more information see
:ref:`development_manual/testing`.
