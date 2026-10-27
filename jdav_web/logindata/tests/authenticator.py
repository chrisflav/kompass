"""A software WebAuthn authenticator, so tests run real ceremonies end to end.

It answers ``navigator.credentials.create`` and ``.get`` the way a browser with
a security key would, as the JSON the login page's script and the frontend
post: a P-256 key, ``none`` attestation, and genuine signatures that
py_webauthn verifies like any other.
"""

import base64
import hashlib
import json
import os

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from django.conf import settings

UP = 0x01
UV = 0x04
AT = 0x40


def b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


class SoftAuthenticator:
    def __init__(self, user_verification=True, resident=True):
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = os.urandom(32)
        self.user_verification = user_verification
        self.resident = resident
        self.sign_count = 0
        self.user_handle = None

    @property
    def id(self):
        return b64(self.credential_id)

    def _client_data(self, kind, challenge, origin):
        return json.dumps(
            {"type": kind, "challenge": challenge, "origin": origin, "crossOrigin": False}
        ).encode()

    def _flags(self):
        return UP | (UV if self.user_verification else 0)

    def create(self, options, origin=None):
        """The response to creation ``options``, as the frontend posts it."""
        numbers = self.key.public_key().public_numbers()
        public_key = cbor2.dumps(
            {
                1: 2,
                3: -7,
                -1: 1,
                -2: numbers.x.to_bytes(32, "big"),
                -3: numbers.y.to_bytes(32, "big"),
            }
        )
        auth_data = (
            hashlib.sha256(options["rp"]["id"].encode()).digest()
            + bytes([self._flags() | AT])
            + self.sign_count.to_bytes(4, "big")
            + bytes(16)
            + len(self.credential_id).to_bytes(2, "big")
            + self.credential_id
            + public_key
        )
        self.user_handle = options["user"]["id"]
        client_data = self._client_data(
            "webauthn.create", options["challenge"], origin or settings.WEBAUTHN_ORIGINS[0]
        )
        attestation = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
        return {
            "id": self.id,
            "rawId": self.id,
            "type": "public-key",
            "response": {
                "clientDataJSON": b64(client_data),
                "attestationObject": b64(attestation),
            },
            "clientExtensionResults": {"credProps": {"rk": self.resident}},
        }

    def get(self, options, origin=None, user_handle=None):
        """The response to request ``options``, as the login page posts it."""
        self.sign_count += 1
        auth_data = (
            hashlib.sha256(options["rpId"].encode()).digest()
            + bytes([self._flags()])
            + self.sign_count.to_bytes(4, "big")
        )
        client_data = self._client_data(
            "webauthn.get", options["challenge"], origin or settings.WEBAUTHN_ORIGINS[0]
        )
        signature = self.key.sign(
            auth_data + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256())
        )
        return {
            "id": self.id,
            "rawId": self.id,
            "type": "public-key",
            "response": {
                "clientDataJSON": b64(client_data),
                "authenticatorData": b64(auth_data),
                "signature": b64(signature),
                "userHandle": user_handle if user_handle is not None else self.user_handle,
            },
            "clientExtensionResults": {},
        }
