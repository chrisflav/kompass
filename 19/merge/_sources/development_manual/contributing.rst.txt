.. _development_manual/contributing:

============
Contributing
============

Any form of contribution is appreciated. If you found a bug or have a feature request, please file an
`issue <https://git.jdav-hd.merten.dev/digitales/kompass/issues>`_. If you want to help with the documentation or
want to contribute code, please open a `pull request <https://git.jdav-hd.merten.dev/digitales/kompass/pulls>`_.

.. note::

    Please read this page carefully before contributing.

Miscellaneous
-------------

- version control with `git <https://git-scm.com/>`_
- own gitea instance at https://git.jdav-hd.merten.dev/
- protected ``main`` branch

Organization and branches
-------------------------

The stable development happens on the ``main``-branch for which only maintainers have write access. Any pull request
should hence be targeted at ``main``. Regularly, the production instances are updated to the latest ``main`` version,
in particular these are considered to be stable.

If you have standard write access to the repository, feel free to create new branches.  To make organization
easier, please follow the branch naming convention: ``<username>/<feature>``.

The ``testing``-branch is deployed on the development instances. No development should happen there, this branch
is regularly reset to the ``main``-branch.


Workflow
--------

- request a gitea account from the project maintainers
- decide on an `issue <https://git.jdav-hd.merten.dev/digitales/kompass/issues>`_ to work on or create a new one
- branch out to an own branch (naming convention: ``<username>/<feature>``) from the ``main``-branch
- work on the issue and commit your changes
- create a pull request from your branch to the ``main``-branch


.. _development_manual/contributing/documentation:

Documentation
-------------

If you want to contribute to the documentation, please follow the steps below.

Online (latest release version): https://jdav-hd.de/static/docs/

- This documentation is build `sphinx <https://www.sphinx-doc.org/>`_ and `awsome sphinx theme <https://sphinxawesome.xyz/>`_ the source code is located in ``docs/``. 
- All documentation is written in `reStructuredText <https://www.sphinx-doc.org/en/master/usage/restructuredtext/index.html>`_ and uses the `sphinx directives <https://www.sphinx-doc.org/en/master/usage/restructuredtext/directives.html>`_.
    - The directives can vary due to the theme, see the `awesome sphinx theme documentation <https://sphinxawesome.xyz/demo/notes/>`_. 
- All technical documentation is written in english, user documentation is written in german.

To read the documentation build it locally and view it in your browser:

.. code-block:: bash

    cd docs/
    make html

    # MacOS (with firefox)
    open -a firefox $(pwd)/docs/build/html/index.html 
    # Linux (I guess?!?)
    firefox ${pwd}/docs/build/html/index.html 

Code
----

If you want to contribute code, please follow the inital setup steps in the :ref:`development_manual/setup` section. And dont forget to :ref:`document <development_manual/contributing/documentation>` your code properly and write tests.


.. note:: 
    
    Still open / to decide:

    - linting 
    - (auto) formatting
    - reliable tests via ci/cd pipeline

