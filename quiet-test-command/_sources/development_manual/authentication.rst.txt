.. _development_manual/authentication:

==============
Authentication
==============

By default, Kompass uses Django's builtin authentication backend for logging into
the admin pages. For integrating third-party services, Kompass can both authenticate
against a third-party service or provide authentication for third-party services.

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
