"""Tests for signed approval records in governance middleware."""

import pytest

from oas_core.middleware.governance import GovernanceMiddleware

# Only run if PyNaCl is available
try:
    import nacl.signing  # type: ignore[import-untyped]
    HAS_NACL = True
except ImportError:
    HAS_NACL = False


@pytest.mark.skipif(not HAS_NACL, reason="PyNaCl not installed")
class TestSignedApprovals:
    def test_sign_and_verify(self):
        key = nacl.signing.SigningKey.generate()
        seed = bytes(key)

        approval = {
            "approval_id": "ap_123",
            "status": "approved",
            "campaign_id": "camp_1",
            "requested_by": "leader",
        }

        signed = GovernanceMiddleware.sign_approval(approval, seed)
        assert "signature" in signed
        assert "signer_public_key" in signed

        assert GovernanceMiddleware.verify_approval_signature(signed) is True

    def test_verify_rejects_tampered(self):
        key = nacl.signing.SigningKey.generate()
        seed = bytes(key)

        approval = {"approval_id": "ap_456", "status": "approved"}
        signed = GovernanceMiddleware.sign_approval(approval, seed)

        # Tamper with the data
        signed["status"] = "rejected"
        assert GovernanceMiddleware.verify_approval_signature(signed) is False

    def test_verify_missing_signature(self):
        assert GovernanceMiddleware.verify_approval_signature({}) is False

    def test_sign_preserves_original_data(self):
        key = nacl.signing.SigningKey.generate()
        seed = bytes(key)

        original = {"approval_id": "ap_789", "status": "approved", "notes": "ok"}
        signed = GovernanceMiddleware.sign_approval(original, seed)

        assert signed["approval_id"] == "ap_789"
        assert signed["status"] == "approved"
        assert signed["notes"] == "ok"
