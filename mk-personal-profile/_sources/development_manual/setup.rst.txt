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

2. Start docker using Make (recommended)

.. code-block:: bash

    make dev up

This runs the docker in your current shell, which is useful to see any log output. If you want to run
the development server in the background instead, use ``make dev up detach=true``.

During the initial run, the container is built and all dependencies are installed which can take a few minutes.
After successful installation, the Kompass initialization runs, which in particular sets up all tables in the
database.

If you need to rebuild the container (e.g. after changing the ``requirements.txt``), execute

.. code-block:: bash

    make dev build

3. Setup admin user: in a separate shell, while the docker container is running, execute

.. code-block:: bash

    make dev manage createsuperuser

This creates an admin user for the administration interface.

Alternative: Using docker compose directly
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If you prefer to use ``docker compose`` commands directly instead of the Make targets, you need to manually
export the USER_ID, GROUP_ID, and USERNAME environment variables. These variables ensure that the owner of the
``/app/jdav_web`` directory in the Docker container matches your user, allowing automatic rebuilding upon
changes in the source.

.. code-block:: bash

    cd docker/development
    export USER_ID=$(id -u)
    export GROUP_ID=$(id -g)
    export USERNAME=$(id -un)
    docker compose up

You will need to export these variables every time you open a new shell before running ``docker compose`` commands.
The Make targets handle this automatically, which is why they are the recommended approach.


Development
-----------

If the initial installation was successful, you can start developing. Changes to files cause an automatic
reload of the development server. If you need to generate and perform database migrations or generate locale files,
you can run Django management commands directly:

.. code-block:: bash

    make dev manage migrate
    make dev manage makemigrations
    make dev manage createsuperuser

For more complex tasks requiring multiple commands, you can open a shell in the container:

.. code-block:: bash

    make dev shell
    cd jdav_web
    python3 manage.py <command>

For more information on Django management commands, see the https://docs.djangoproject.com/en/4.0/ref/django-admin.

Make commands reference
~~~~~~~~~~~~~~~~~~~~~~~~

The following Make commands are available for development:

- ``make dev build`` - Build the development containers
- ``make dev build BUILD_ARGS=--no-cache`` - Build without using cached layers (useful when dependencies change)
- ``make dev build BUILD_ARGS="--no-cache --pull"`` - Build with multiple docker compose arguments
- ``make dev up`` - Start the development environment in foreground
- ``make dev up detach=true`` - Start the development environment in background
- ``make dev down`` - Stop the development environment
- ``make dev shell`` - Open a bash shell in the running container
- ``make dev manage <command>`` - Run a Django management command (e.g., ``make dev manage migrate``)

Additional docker compose build arguments can be passed using the ``BUILD_ARGS`` variable, such as ``--no-cache``,
``--pull``, or ``--progress=plain``. For multiple arguments, quote them: ``BUILD_ARGS="--no-cache --pull"``.




Known Issues
------------

- If you use ``docker compose`` directly without exporting the ``USER_ID``, ``GROUP_ID``, and ``USERNAME`` variables,
  you will encounter the following error message after running ``docker compose up``:

.. code-block:: bash

    => ERROR [master 6/7] RUN groupadd -g  fritze && useradd -g  -u  -m -d /app fritze                                                                                                                0.2s
    ------
    > [master 6/7] RUN groupadd -g  fritze && useradd -g  -u  -m -d /app fritze:
    0.141 groupadd: invalid group ID 'fritze'
    ------
    failed to solve: process "/bin/sh -c groupadd -g $GID $USER && useradd -g $GID -u $UID -m -d /app $USER" did not complete successfully: exit code: 3

In this case, either:

- Use the Make commands (``make dev up``) which handle variable exports automatically (recommended), or
- Export the required variables as shown in the "Alternative: Using docker compose directly" section above
