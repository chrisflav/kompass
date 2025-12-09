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

2. Add ``docker/development/docker.env`` (you may copy and rename the provided ``docker.env.example``) and ``docker/development/config/settings.toml`` file (you may copy and rename the provided ``settings.toml.example``).

3. Start docker using Make (recommended)

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

4. Setup admin user: in a separate shell, while the docker container is running, execute

.. code-block:: bash

    make dev createsuperuser

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
reload of the development server. If you need to generate and perform database migrations, generate locale files,
or run tests, you can use make commands. The most common command generates and compiles translation files:

.. code-block:: bash

    make dev translate # generate and compile translation files

For more Info about the translation workflow, see https://docs.djangoproject.com/en/5.2/ref/django-admin/#django-admin-makemessages
For less common tasks, you can use the ``shell`` command, to enter the container shell and run any Django management commands:

.. code-block:: bash

    make dev shell

In the container shell, you can run Django management commands, such as:

.. code-block:: bash

    python3 manage.py makemigrations # run when you made changes to the data models
    python3 manage.py migrate # run to apply database migrations
    python3 manage.py import_members members/test_data/members.csv # import example members data from CSV file
    python3 manage.py test members.tests.view.ConfirmInvitationViewTestCase # run specific tests or test modules
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
- ``make dev shell`` - Open the container shell to run Django management commands
- ``make dev createsuperuser`` - Create a Django superuser account
- ``make dev translate`` - Generate and compile translation files (runs ``makemessages`` and ``compilemessages``)

Additional docker compose build arguments can be passed using the ``BUILD_ARGS`` variable, such as ``--no-cache``,
``--pull``, or ``--progress=plain``. For multiple arguments, quote them: ``BUILD_ARGS="--no-cache --pull"``.


Email Configuration
~~~~~~~~~~~~~~~~~~~

By default, the development environment is configured to use the **console email backend**, which means that
emails are not actually sent but instead are printed to the console output. This is useful for development
as it allows you to see what emails would be sent without requiring a mail server or risking accidentally
sending emails during development.

To switch from the console backend to actually sending emails via SMTP, you need to modify the
``docker/development/config/settings.toml`` file:

1. Set ``use_console_backend = false`` in the ``[mail]`` section
2. Configure the SMTP server credentials:

.. code-block:: toml

    [mail]
    host = 'smtp.example.com'
    user = 'user@example.com'
    password = 'your-password'
    default_sending_address = 'info@example.com'
    default_sending_name = 'Your Organization'
    use_console_backend = false  # Set to false to send actual emails

When ``use_console_backend = true`` (the default for development), the SMTP configuration is ignored and
all emails are printed to the console where you can inspect their content.


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
