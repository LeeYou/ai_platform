"""
License signing and verification using RSA-SHA256 via the `cryptography` library.

Canonical JSON: sorted keys, no spaces, excluding the "signature" field.
Signature: RSA-PSS with SHA-256, stored as base64 in the "signature" field.
"""

import base64
import json
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import (
    RSAPrivateKey,
    RSAPublicKey,
    generate_private_key,
)
from cryptography.exceptions import InvalidSignature


def _canonical_json(data: dict[str, Any]) -> bytes:
    """Return deterministic JSON bytes, excluding the 'signature' field."""
    payload = {k: v for k, v in data.items() if k != "signature"}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def sign_license(license_data: dict[str, Any], privkey_pem: str) -> str:
    """
    Sign *license_data* with *privkey_pem* (PEM-encoded RSA private key).

    Returns the full license JSON string with a base64-encoded RSA-SHA256
    signature injected as the "signature" field.
    """
    private_key: RSAPrivateKey = serialization.load_pem_private_key(
        privkey_pem.encode("utf-8") if isinstance(privkey_pem, str) else privkey_pem,
        password=None,
    )

    canonical = _canonical_json(license_data)

    signature_bytes = private_key.sign(
        canonical,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH,
        ),
        hashes.SHA256(),
    )

    signed_data = dict(license_data)
    signed_data["signature"] = base64.b64encode(signature_bytes).decode("ascii")
    return json.dumps(signed_data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def verify_license(license_json: str, pubkey_pem: str) -> bool:
    """
    Verify *license_json* against *pubkey_pem* (PEM-encoded RSA public key).

    Returns True if the signature is valid, False otherwise.
    """
    try:
        data = json.loads(license_json)
        signature_b64 = data.get("signature")
        if not signature_b64:
            return False

        public_key: RSAPublicKey = serialization.load_pem_public_key(
            pubkey_pem.encode("utf-8") if isinstance(pubkey_pem, str) else pubkey_pem
        )

        signature_bytes = base64.b64decode(signature_b64)
        canonical = _canonical_json(data)

        public_key.verify(
            signature_bytes,
            canonical,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH,
            ),
            hashes.SHA256(),
        )
        return True
    except (InvalidSignature, Exception):
        return False


def generate_key_pair(key_size: int = 2048) -> tuple[str, str]:
    """
    Generate a new RSA key pair.

    Returns ``(private_key_pem, public_key_pem)`` as PEM strings.
    """
    private_key = generate_private_key(public_exponent=65537, key_size=key_size)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")

    public_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )
    return private_pem, public_pem
