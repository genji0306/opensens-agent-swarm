"""Tests for shared.crypto — Ed25519 key generation, signing, and verification."""
import base64
from pathlib import Path

import pytest

from shared.crypto import generate_keypair, sign_payload, verify_signature, load_signing_key


@pytest.fixture
def key_dir(tmp_path):
    return tmp_path / "keys"


@pytest.fixture
def keypair(key_dir):
    return generate_keypair(key_dir)


class TestGenerateKeypair:
    def test_creates_key_files(self, keypair, key_dir):
        priv, pub = keypair
        assert priv.exists()
        assert pub.exists()
        assert priv.name == "signing.key"
        assert pub.name == "signing.pub"

    def test_private_key_permissions(self, keypair):
        priv, _ = keypair
        mode = priv.stat().st_mode & 0o777
        assert mode == 0o600

    def test_keys_are_valid_base64(self, keypair):
        priv, pub = keypair
        base64.b64decode(priv.read_bytes())
        base64.b64decode(pub.read_bytes())


class TestSignAndVerify:
    def test_roundtrip(self, keypair):
        priv, pub = keypair
        payload = {"action": "research", "topic": "quantum sensors"}
        sig = sign_payload(payload, priv)
        assert verify_signature(payload, sig, pub)

    def test_different_payload_fails(self, keypair):
        priv, pub = keypair
        payload = {"action": "research"}
        sig = sign_payload(payload, priv)
        assert not verify_signature({"action": "other"}, sig, pub)

    def test_corrupted_signature_fails(self, keypair):
        priv, pub = keypair
        payload = {"key": "value"}
        sig = sign_payload(payload, priv)
        corrupted = "00" + sig[2:]
        assert not verify_signature(payload, corrupted, pub)

    def test_signature_is_hex_string(self, keypair):
        priv, _ = keypair
        sig = sign_payload({"test": True}, priv)
        assert isinstance(sig, str)
        bytes.fromhex(sig)  # Should not raise

    def test_deterministic_for_same_payload(self, keypair):
        priv, _ = keypair
        payload = {"a": 1, "b": 2}
        sig1 = sign_payload(payload, priv)
        sig2 = sign_payload(payload, priv)
        # Ed25519 signatures are deterministic
        assert sig1 == sig2

    def test_key_order_independent(self, keypair):
        priv, pub = keypair
        sig = sign_payload({"b": 2, "a": 1}, priv)
        assert verify_signature({"a": 1, "b": 2}, sig, pub)


class TestLoadSigningKey:
    def test_load_generated_key(self, keypair):
        priv, _ = keypair
        key = load_signing_key(priv)
        assert key is not None
