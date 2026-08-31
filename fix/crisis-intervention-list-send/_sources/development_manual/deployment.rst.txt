.. _development_manual/deployment:

=====================
Production Deployment
=====================

The production setup is based on the docker configuration in the ``production/`` folder of the repository. In
contrast to the development setup, there is no database service configured in the ``docker-compose.yaml``. This
is to allow for a more flexible setup with a database service installed on the host, for which it is easier
to ensure data safety.

.. _user_manual/initial_installation:

Initial installation
====================

We give here step-by-step instructions how to set up an initial Kompass installation starting from a fresh
Debian Bookworm installation. Of course these steps can be easily adapted to a different Linux distribution,
the steps will mostly differ in the way the system dependencies are installed.

The instructions describe the recommended setup with a docker-independent MySQL database server on the host system.

We assume that all instructions are executed as ``root`` or with ``sudo``.

1. Install the dependencies: To install ``docker``, please follow the `official instructions`_. For the MySQL
   server, run the following command:

   .. code-block:: console

      apt install mariadb-server

2. Setup the database: We need to create the database and create a user with a strong password. To generate
   a strong password, run

   .. code-block:: console

      PASSWORD=$(tr -dc 'A-Za-z0-9' < /dev/urandom | head -c 24)

   Now create a MySQL user with the generated password, by executing:

   .. code-block:: console

      mysql <<EOF
      CREATE USER 'kompass'@'10.26.42.0/255.255.255.0' IDENTIFIED BY '$PASSWORD';
      GRANT ALL PRIVILEGES ON kompass.* to 'kompass'@'10.26.42.0/255.255.255.0';
      FLUSH PRIVILEGES;
      EOF

   To make the MySQL server available from the docker container, edit ``/etc/mysql/mariadb.cnf`` and
   uncomment the ``port`` line in the ``[client-server]`` code block. It could then look like this:

   .. code-block:: console

      [client-server]
      port = 3306
      socket = /run/mysqld/mysqld.sock

   Finally, edit ``/etc/mysql/mariadb.conf.d/50-server.cnf`` and add ``10.26.42.1`` [#ip-address]_ to the
   ``bind-address`` line. It could then look like this:

   .. code-block:: console

      bind-address  = 127.0.0.1,10.26.42.1

   Now restart the MySQL database by running:

   .. code-block:: console

      systemctl restart mariadb.service

   .. note::
      If you are running a firewall service, you will need to allow connections to the ``3306`` port
      from the ``10.26.42.0/24`` subnet. If you use ``ufw``, you can do:

      .. code-block:: console

         ufw allow from 10.26.42.0/24 to 10.26.42.1 port 3306

3. Install Kompass:

   .. code-block:: console

      mkdir /opt/kompass
      cd /opt/kompass

   Copy the contents of the ``deploy/`` directory of the Kompass repository into this folder. Afterwards,
   the folder structure should look like this:

   .. code-block::

      .
      ├── config
      │   └── settings.toml
      └── docker-compose.yaml

   .. note::
      As long as the Kompass repository is private, you need to ask the maintainers to add a read-only deploy
      key for your installation to the `Gitea`_. Then you can add a ``.ssh`` config file on your server with a
      section

      .. code-block:: console

         Host git.jdav-hd.merten.dev
             HostName git.jdav-hd.merten.dev
             User git
             IdentityFile ~/.ssh/your_deploy_key

   Now set the password of the MySQL user in the ``settings.toml`` by running

   .. code-block:: console

      sed -i "s/kompass-db-user-password/$PASSWORD/g" config/settings.toml

   Finally, we can start the docker containers for the first time by running:

   .. code-block:: console

      docker compose up --build

   This will start building the docker images and then launch the application. If everything
   works as expected, there should be no error messages. In this case open a second terminal,
   navigate to ``/opt/kompass/`` and run

   .. code-block:: console

      docker compose exec master bash
      cd jdav_web
      python3 manage.py createsuperuser

   This will prompt you for a username and a password for the initial admin user. Use a strong password
   and don't use the same password as the one for the MySQL user above!

   The webserver will be available on ``localhost`` on port ``3000``. To expose it to the
   outer world, we need to setup a web server, such as ``apache2``.

4. Install a webserver: This is standard and not Kompass specific, but we still include the
   steps here for completeness. First, we need to install ``apache2``:

   .. code-block:: console

      apt install apache2
      a2enmod md ssl proxy proxy_http headers

   To allow the ``md`` module to automatically request a Let's Encrypt certificate for our domain,
   you need to accept the `certificate agreement`_. If you do, add the following line

   .. code-block::

      MDCertificateAgreement accepted

   to ``/etc/apache2/apache2.conf``.

   Then create a new file ``/etc/apache2/sites-available/kompass.conf`` with

   .. code-block::

      MDomain jdav-town.de

      <VirtualHost *:443>
          ServerName jdav-town.de
          ServerAdmin digital@jdav-town.de

          SSLEngine on
          SSLOptions      StrictRequire

          ErrorLog   /var/log/apache2/error.log
          LogLevel warn

          CustomLog /var/log/apache2/access.log vhost_combined
          SSLProxyEngine on

          ProxyPass / http://localhost:3000/
          ProxyPassReverse / http://localhost:3000/
          RequestHeader set X-Forwarded-Proto "https"
          RequestHeader set X-Forwarded-Ssl on
          RequestHeader set X-Forwarded-Port 443

      </VirtualHost>

   Replace the ``jdav-town.de`` domain by a domain pointing to your server. Now activate the site
   and restart apache:

   .. code-block:: console

      a2ensite kompass.conf
      systemctl restart apache2

   The ``md`` module should now request an SSL certificate from Let's Encrypt, while this is still
   pending you will receive a *connection not secure* error when visiting your domain. Check
   ``/var/log/apache2/error.log`` for any possible errors. If everything worked, you will find there a
   message similar to:

   .. code-block::

      [Mon Feb 10 ...] ... : The Managed Domain ... has been setup and changes will be activated on next (graceful) server restart.

   In this case run

   .. code-block:: console

      systemctl restart apache2

   again. You should now see the Kompass application at your domain!

5. Update settings: Adapt ``/opt/kompass/config/settings.toml`` to your needs. If you followed the guide
   as above, there should be no need to change anything in the ``[database]`` section.

   .. note::
      We recommend to initialize a ``git`` repository in the ``config`` folder to version control any changes
      to the local configuration.

6. Run the container in background mode: If everything is working, you can cancel the
   ``docker compose up --build`` command from above and run

   .. code-block:: console

     docker compose up -d --build

   Whenever you change your configuration or want to update to the latest version,
   run this command again.

7. Setup mail configuration: The Kompass application needs a working mailserver for forwarding incoming
   mails on personal mail accounts and on configured forward mail addresses. You can either setup
   a mailserver on your own or use the docker-based `Kompass-tailored mailserver`_.

   For receiving mails, no further changes to the ``settings.toml`` are needed. For sending mails,
   the ``[mail]`` sections needs to be updated with authentication details for an SMTP server.

   If you are using (and have already installed) the docker-based mailserver, proceed as follows:
   In the Kompass administrative interface create a new user account (i.e. login data) with
   a strong password and without staff access. Then update the ``[mail]`` section
   in the ``settings.toml`` accordingly with the created user name and password.
   The ``host = 'host'`` setting is correct in this case and points to the underlying host.


Local configuration
===================

If you followed the steps outlined in :ref:`user_manual/initial_installation`, you have a folder
``/opt/kompass/config`` currently containing only a ``settings.toml``.

While the ``settings.toml`` configures the most important options,
in practice you might want to have more control over texts on the website, used logos
or texts used in automatically generated emails. Here we will explain how to configure these.

- Mail texts: To modify the standard email texts, create a file ``texts.toml`` in your config
  directory. This could then for example look like this:

  .. code-block::

     confirm_mail = """
     Hello {name},

     please confirm your email address! For this use the cool link at {link}.

     ..."""

     new_unconfirmed_registration = """
     Hi {name},

     your group {group} has a new registration! ..."""

- Templates: To override ``.html`` of the Kompass application, create a directory ``templates`` inside
  your config directory. This is loaded as a regular templates directory by ``django``, hence
  you can override anything that lives in one of the many ``templates`` directories in the main repository.

  For example, to fill the impressum page with content, you need to create a file
  ``templates/startpage/impressum_content.html``. In this file you can put any ``.html`` document and this
  will be placed in the impressum page.

  Typical templates to override here are (with their respective paths):

  - ``templates/startpage/impressum_content``: impressum page
  - ``templates/startpage/faq_content``: group registration FAQ
  - ``templates/startpage/group_introduction``: introductory text placed above the group listing

.. rubric:: Footnotes

.. [#ip-address] The choice of the subnet ``10.26.42.0/24`` is arbitrarily chosen
   from the `list of private IPv4 addresses`_. If by coincidence this specific subnet
   is already used on your system, you can replace this by any other subnet from the linked
   list. Note that in this case you need to replace all references to ``10.26.42.0/24``
   and ``10.26.42.1`` by your choice, including in the ``networks`` section
   of the ``docker-compose.yaml``.

.. _official instructions: https://docs.docker.com/engine/install/debian/
.. _Gitea: https://git.jdav-hd.merten.dev/digitales/kompass
.. _list of private IPv4 addresses: https://en.wikipedia.org/wiki/Private_network#Private_IPv4_addresses
.. _certificate agreement: https://letsencrypt.org/documents/LE-SA-v1.4-April-3-2024.pdf
.. _Kompass-tailored mailserver: https://git.jdav-hd.merten.dev/digitales/kompass-mailserver
