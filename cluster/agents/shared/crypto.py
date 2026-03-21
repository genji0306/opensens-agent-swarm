"""Ed25519 signing and verification using PyNaCl."""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

from nacl.signing import SigningKey, VerifyKey
from nacl.exceptions import BadSignatureError


def load_signing_key(path: Path) -> SigningKey:
    raw = path.read_bytes()
    return SigningKey(base64.b64decode(raw))


def load_verify_key(path: Path) -> VerifyKey:
    raw = path.read_bytes()
    return VerifyKey(base64.b64decode(raw))


def sign_payload(payload: dict, key_path: Path) -> str:
    key = load_signing_key(key_path)
    payload_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).digest()
    signed = key.sign(payload_hash)
    return signed.signature.hex()


def verify_signature(payload: dict, signature_hex: str, pub_key_path: Path) -> bool:
    try:
        vk = load_verify_key(pub_key_path)
        payload_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode()
        ).digest()
        vk.verify(payload_hash, bytes.fromhex(signature_hex))
        return True
    except (BadSignatureError, ValueError):
        return False


def generate_keypair(key_dir: Path) -> tuple[Path, Path]:
    key_dir.mkdir(parents=True, exist_ok=True)
    sk = SigningKey.generate()

    private_path = key_dir / "signing.key"
    public_path = key_dir / "signing.pub"

    private_path.write_bytes(base64.b64encode(bytes(sk)))
    private_path.chmod(0o600)
    public_path.write_bytes(base64.b64encode(bytes(sk.verify_key)))

    return private_path, public_path
