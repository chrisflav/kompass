.. _development_manual/setup:

=================
Development Setup
=================

The project is run with ``docker`` and all related files are in the ``docker/`` subfolder. Besides the actual Kompass
application, a database (postgresql) and a broker (redis) are setup and run in the docker container. No
external services are needed for running the development container.

Initial installation
--------------------

A working ``docker`` setup (with ``docker compose``) is required. For installation instructions see the
`docker manual <https://docs.docker.com/engine/install/>`_.

1. Clone the repository and change into the directory of the repository.

2. Fetch submodules

.. code-block:: bash

    git submodule update --init


.. _step-3:

3. Prepare development environment: to allow automatic rebuilding upon changes in the source,
   the owner of the ``/app/jdav_web`` directory in the Docker container must match your
   user. For this, make sure that the output of ``echo UID`` and ``echo UID`` is not empty. Then run

.. code-block:: bash

    export GID=${GID}
    export UID=${UID}

4. Start docker

.. code-block:: bash

    cd docker/development
    docker compose up

This runs the docker in your current shell, which is useful to see any log output. If you want to run
the development server in the background instead, use ``docker compose up -d``.

During the initial run, the container is built and all dependencies are installed which can take a few minutes.
After successful installation, the Kompass initialization runs, which in particular sets up all tables in the
database.

If you need to rebuild the container (e.g. after changing the ``requirements.txt``), execute

.. code-block:: bash

    docker compose up --build

5. Setup admin user: in a separate shell, while the docker container is running, execute

.. code-block:: bash

    cd docker/development
    docker compose exec master bash -c "cd jdav_web && python3 manage.py createsuperuser"

This creates an admin user for the administration interface.


Development
-----------

If the initial installation was successful, you can start developing. Changes to files cause an automatic
reload of the development server. If you need to generate and perform database migrations or generate locale files,
use

.. code-block:: bash

    cd docker/development
    docker compose exec master bash
    cd jdav_web

This starts a shell in the container, where you can execute any django maintenance commands via
``python3 manage.py <command>``. For more information, see the https://docs.djangoproject.com/en/4.0/ref/django-admin.




Known Issues
------------

- If the ``UID`` and ``GID`` variables are not setup properly, you will encounter the following error message
  after running ``docker compose up``.

.. code-block:: bash

    => ERROR [master 6/7] RUN groupadd -g  fritze && useradd -g  -u  -m -d /app fritze                                                                                                                0.2s
    ------
    > [master 6/7] RUN groupadd -g  fritze && useradd -g  -u  -m -d /app fritze:
    0.141 groupadd: invalid group ID 'fritze'
    ------
    failed to solve: process "/bin/sh -c groupadd -g $GID $USER && useradd -g $GID -u $UID -m -d /app $USER" did not complete successfully: exit code: 3

In this case repeat :ref:`step 3 <step-3>` above.
