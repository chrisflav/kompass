# kompass

[![Build Status](https://jenkins.merten.dev/buildStatus/icon?job=gitea%2Fkompass%2Fmain)](https://jenkins.merten.dev/job/gitea/job/kompass/job/main/)

Kompass is an administration platform designed for local sections of the Young German Alpine Club. It provides
tools to contact and (automatically) manage members, groups, material, excursions and statements.

For more details on the features, see the (German) [documentation](https://jdav-hd.de/static/docs/index.html).

# Contributing

Any form of contribution is appreciated. If you found a bug or have a feature request, please file an
[issue](https://git.jdav-hd.merten.dev/digitales/kompass/issues). If you want to help with the documentation or
want to contribute code, please open a [pull request](https://git.jdav-hd.merten.dev/digitales/kompass/pulls).

The following is a short description of the development setup and an explanation of the various
branches.

## Development setup

The project is run with `docker` and all related files are in the `docker/` subfolder. Besides the actual Kompass
application, a database (postgresql) and a broker (redis) are setup and run in the docker container. No
external services are needed for running the development container.

### Initial installation

A working `docker` setup (with `docker compose` support) is required. For installation instructions see the
[docker manual](https://docs.docker.com/engine/install/).

1. Clone the repository and change into the directory of the repository.

2. Fetch submodules
   ```bash
   git submodule update --init
   ```

3. Prepare development environment: to allow automatic rebuilding upon changes in the source,
   the owner of the `/app/jdav_web` directory in the docker container must agree with
   your user. For this, make sure that the output of `echo UID` and `echo UID` is not empty. Then run
   ```bash
   export GID=${GID}
   export UID=${UID}
   ```

4. Start docker
   ```bash
   cd docker/development
   docker compose up
   ```
   This runs the docker in your current shell, which is useful to see any log output. If you want to run
   the development server in the background instead, use `docker compose up -d`.

   During the initial run, the container is built and all dependencies are installed which can take a few minutes.
   After successful installation, the Kompass initialization runs, which in particular sets up all tables in the
   database.

5. Setup admin user: in a separate shell, while the docker container is running, run
   ```bash
   cd docker/development
   docker compose exec master bash -c "cd jdav_web && python3 manage.py createsuperuser"
   ```
   This creates an admin user for the administration interface.

### Development

If the initial installation was successful, you can start developing. Changes to files cause an automatic
reload of the development server. If you need to generate and perform database migrations or generate locale files,
use
```
cd docker/development
docker compose exec master bash
cd jdav_web
```
This starts a shell in the container, where you can execute any django maintenance commands via
`python3 manage.py <command>`. For more information, see the [django documentation](https://docs.djangoproject.com/en/4.0/ref/django-admin).

### Testing

To run the tests, you can use the docker setup under `docker/test`.

### Known Issues

- If the `UID` and `GID` variables are not setup properly, you will encounter the following error message
  after running `docker compose up`.

  ```bash
  => ERROR [master 6/7] RUN groupadd -g  fritze && useradd -g  -u  -m -d /app fritze                                                                                                                0.2s
  ------
  > [master 6/7] RUN groupadd -g  fritze && useradd -g  -u  -m -d /app fritze:
  0.141 groupadd: invalid group ID 'fritze'
  ------
  failed to solve: process "/bin/sh -c groupadd -g $GID $USER && useradd -g $GID -u $UID -m -d /app $USER" did not complete successfully: exit code: 3
  ```
  In this case repeat step 3 above.

## Organization and branches

The stable development happens on the `main` branch for which only maintainers have write access. Any pull request
should hence be targeted at `main`. Regularly, the production instances are updated to the latest `main` version,
in particular these are considered to be stable.

If you have standard write access to the repository, feel free to create new branches. To make organization
easier, please indicate your username in the branch name.

The `testing` branch is deployed on the development instances. No development should happen there, this branch
is regularly reset to the `main` branch.
