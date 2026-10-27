.. _development_manual/authentication:

==============
Authentication
==============

By default, Kompass uses Django's builtin authentication backend for logging into
the admin pages. For integrating third-party services, Kompass can both authenticate
against a third-party service or provide authentication for third-party services.

The new frontend signs in differently: it sends the browser to the OAuth2
provider mounted at ``/o/`` using Authorization Code + PKCE, and then calls the
REST API with the bearer token it gets back. The password is typed on a page
Django serves — the frontend never sees it. Where OIDC is configured that page
is the provider's; otherwise it is Django's own form at ``/accounts/login/``,
which is mounted outside the language prefixes so it stays reachable on whatever
domain the frontend is served from. See
:ref:`development_manual/deployment` for registering the application.

Two-factor authentication
-------------------------

Where Kompass checks passwords itself (OIDC is off), every user can add second
factors from the frontend: authenticator apps (TOTP), WebAuthn security keys and
passkeys, and ten one-time recovery codes. It is optional for everyone.

A user with a second factor who gives the right password at ``/accounts/login/``
is not logged in yet. The session only notes the account, the password hash's
fingerprint and a five-minute deadline, and ``/accounts/login/two-factor/``
calls ``login()`` once a factor checks out. ``/o/authorize/`` therefore never
sees a half-authenticated session. A passkey (a discoverable credential created
with user verification) also logs in on its own from the login page's "Mit
Sicherheitsschlüssel anmelden" button. The admin's own login form under
``/kompass`` is replaced by a redirect to ``/accounts/login/``, and the OAuth2
*password* grant is refused for accounts with a second factor, so neither is a
way around it.

Attempts are counted per account before they are checked: every five of them
without a successful second factor lock the second step, first for fifteen
minutes, then twice as long each further time, up to a day. Attempts to confirm
the frontend's 2FA settings count too. The first lock is mailed to the user, once
until a second factor succeeds again. Adding the first factor revokes the
account's other OAuth2 tokens (not the session doing it, nor personal access
tokens): a token obtained with the password alone does not outlive it.

The frontend's 2FA settings first confirm who is signed in
(``POST /api/logindata/two-factor/confirm``): with a second factor where the
account has one, with the password where it has none. That elevates the access
token it was made with, and only it, for ten minutes; every endpoint that shows
or changes factors requires the elevation.

TOTP secrets are stored encrypted with a key derived from ``SECRET_KEY``. When
rotating it, keep the old key in Django's ``SECRET_KEY_FALLBACKS``, or every
authenticator app has to be set up again; Kompass logs an error for each app it
can no longer decrypt, and does not count those logins against the user.
Recovery codes are stored hashed. Personal access tokens are unaffected: they
are created after signing in.

An account's factors can be removed by anyone with ``auth.change_user`` (a
superuser's only by a superuser) from the user's page in the frontend. Each such
reset is logged as a warning by ``logindata.api.admin_router``. The user is
mailed when a factor is removed or reset. The mails' texts can be changed in
``texts.toml`` as ``two_factor_locked``, ``two_factor_removed`` (with
``{factor}``) and ``two_factor_reset``, each with ``{name}``.

Configuration
^^^^^^^^^^^^^

WebAuthn ties a security key to a *relying party ID*, a domain, and accepts it
only on the listed origins. Each origin must be that domain or a subdomain of
it. The defaults usually fit:

.. code-block:: toml

    [two_factor]
    # Default: the host part of [django] host.
    webauthn_rp_id = 'jdav-town.de'
    # Default: "<protocol>://<host>", [django] frontend_base_url and
    # [django] csrf_trusted_origins, i.e. every origin serving /accounts/login/.
    webauthn_origins = ['https://jdav-town.de', 'https://neu.jdav-town.de']
    # The name a browser shows when creating a key, and the issuer in
    # authenticator apps. Default: "Kompass".
    webauthn_rp_name = 'Kompass JDAV Town'

In the production setup the frontend and ``/accounts/`` share one origin, so a
key registered in the frontend's settings works on its login page. If the
frontend runs on a subdomain of ``host`` (``neu.jdav-town.de`` next to
``jdav-town.de``), the default relying party ID covers both. If it runs on an
unrelated domain, set ``webauthn_rp_id`` to the frontend's domain: keys then
only work there, and the old interface's login falls back to the other factors.

Changing ``webauthn_rp_id`` later invalidates every registered security key.

Using Kompass as an OAuth2 Provider
-----------------------------------

Kompass can act as an OAuth2/OIDC provider for other applications.

Configuration
^^^^^^^^^^^^^

Generate an RSA key pair:

.. code-block:: bash

    openssl genrsa -out oidc_private.key 4096
    cat oidc_private.key  # Copy to settings.toml

Then add your private key to ``settings.toml``:

.. code-block:: toml

    [oauth]
    oidc_rsa_private_key = """
    -----BEGIN PRIVATE KEY-----
    your-private-key-here
    -----END PRIVATE KEY-----
    """

Registering Client Applications
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

To add a new client application, navigate to ``https://your-domain.de/o/applications/``
and follow the instructions.

Using Third-Party OIDC Authentication
-------------------------------------

Kompass can authenticate users against an external OpenID Connect provider
(e.g., Authentik, Keycloak, Auth0, Okta).

Configuration
^^^^^^^^^^^^^

Add the following section to your ``settings.toml`` file:

.. code-block:: toml

    [oidc]
    # Enable OIDC authentication
    enabled = true
    # Relying Party (RP) client ID from your OIDC provider
    rp_client_id = 'your-client-id'
    # Relying Party (RP) client secret from your OIDC provider
    rp_client_secret = 'your-client-secret'
    # OIDC Provider (OP) authorization endpoint URL
    op_authorization_endpoint = 'https://your-provider.example.com/application/o/authorize/'
    # OIDC Provider (OP) token endpoint URL
    op_token_endpoint = 'https://your-provider.example.com/application/o/token/'
    # OIDC Provider (OP) user info endpoint URL
    op_user_endpoint = 'https://your-provider.example.com/application/o/userinfo/'
    # OIDC Provider (OP) JSON Web Key Set (JWKS) endpoint URL
    op_jwks_endpoint = 'https://your-provider.example.com/application/o/jwks/'
    # Signature algorithm for verifying ID tokens (typically RS256)
    rp_sign_algo = 'RS256'
    # Space-separated list of OAuth scopes to request
    rp_scopes = 'openid email profile'
    # Claim name in the ID token containing the username
    claim_username = 'preferred_username'
    # Group name in the ID token that grants staff permissions
    group_staff = 'kompass-staff'
    # Group name in the ID token that grants superuser permissions
    group_superuser = 'kompass-admins'

When OIDC is enabled, the Django admin login redirects to the OIDC provider. Users are automatically created or updated based on the ID token claims. Staff and superuser permissions are granted based on group membership in the ``groups`` claim.

OIDC Provider Setup
^^^^^^^^^^^^^^^^^^^

When registering Kompass in your OIDC provider:

- Set the **Redirect URI** to: ``https://your-kompass-domain.com/oidc/callback/``
- Use **Confidential** client type
- Enable **Authorization Code** grant type
- Include scopes: ``openid``, ``email``, ``profile``
- Ensure the provider sends ``groups`` claim if using permission groups
