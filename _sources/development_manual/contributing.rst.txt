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


Workflow
--------

- request a gitea account from the project maintainers
- decide on an `issue <https://github.com/chrisflav/kompass/issues>`_ to work on or create a new one
- branch out to an own branch (naming convention: ``<username>/<feature>``) from the ``main``-branch
- work on the issue and commit your changes
- create a pull request from your branch to the ``main``-branch


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
    open -a firefox $(pwd)/docs/build/html/index.html
    # Linux
    firefox $(pwd)/docs/build/html/index.html

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
