"""Unit tests for integration credentials cryptographic operations.

Verifies Fernet authenticated encryption, envelope packaging, error handling,
key validation, tampering resistance, and zero-plaintext guarantees.
"""

import json
import pytest
from cryptography.fernet import Fernet

from app.core.config import settings
from app.modules.integrations.crypto import (
    DecryptionFailedException,
    EncryptionKeyInvalidException,
    EncryptionKeyMissingException,
    decrypt_credentials,
    encrypt_credentials,
    has_configured_credentials,
)

VALID_TEST_KEY = "bmV4dXNfY3JtX3Rlc3RfZmVybmV0X2tleV8zMmJ5dGU="
ANOTHER_VALID_KEY = Fernet.generate_key().decode()


def test_round_trip_encryption():
    """Verify that credentials dictionary is successfully encrypted and decrypted."""
    creds = {
        "api_key": "sk_live_secret_value_12345",
        "client_id": "oauth_client_abc",
        "webhook_secret": "whsec_supersecrettoken",
        "nested": {"sub_key": "val", "num": 42},
    }

    envelope = encrypt_credentials(creds, key=VALID_TEST_KEY)

    # Envelope structure checks
    assert isinstance(envelope, dict)
    assert envelope["version"] == 1
    assert envelope["algorithm"] == "fernet"
    assert "ciphertext" in envelope
    assert isinstance(envelope["ciphertext"], str)

    # Ensure ZERO plaintext secret appears anywhere in the serialized envelope
    serialized = json.dumps(envelope)
    assert "sk_live_secret_value_12345" not in serialized
    assert "whsec_supersecrettoken" not in serialized
    assert "oauth_client_abc" not in serialized
    assert "api_key" not in serialized

    # Decrypt and verify equality
    decrypted = decrypt_credentials(envelope, key=VALID_TEST_KEY)
    assert decrypted == creds


def test_empty_credentials_require_no_key():
    """Empty credentials dict or None must return {} without requiring an encryption key."""
    assert encrypt_credentials({}, key=None) == {}
    assert encrypt_credentials(None, key=None) == {}
    assert decrypt_credentials({}, key=None) == {}
    assert decrypt_credentials(None, key=None) == {}


def test_missing_key_rejects_non_empty_credentials(monkeypatch):
    """Attempting to encrypt non-empty credentials without a key must raise EncryptionKeyMissingException."""
    monkeypatch.setattr(settings, "INTEGRATION_ENCRYPTION_KEY", None)

    with pytest.raises(EncryptionKeyMissingException):
        encrypt_credentials({"api_key": "secret"}, key=None)

    envelope = {
        "version": 1,
        "algorithm": "fernet",
        "ciphertext": "some_ciphertext",
    }
    with pytest.raises(EncryptionKeyMissingException):
        decrypt_credentials(envelope, key=None)


def test_invalid_key_rejects_encryption_and_decryption(monkeypatch):
    """Keys that are not valid 32-byte urlsafe-base64 strings must raise EncryptionKeyInvalidException."""
    import base64

    invalid_keys = [
        "short_key",
        "not_base64_encoded_at_all!!",
        base64.urlsafe_b64encode(b"too_short_20_bytes!").decode(),
        base64.urlsafe_b64encode(b"this_key_is_way_too_long_for_fernet_33_bytes!").decode(),
        "   ",
        "",
    ]

    for bad_key in invalid_keys:
        with pytest.raises(
            (EncryptionKeyInvalidException, EncryptionKeyMissingException)
        ):
            encrypt_credentials({"token": "123"}, key=bad_key)


def test_decrypt_with_wrong_valid_key_fails_safely():
    """Decrypting ciphertext with a different valid Fernet key must fail safely."""
    creds = {"secret": "my_val"}
    envelope = encrypt_credentials(creds, key=VALID_TEST_KEY)

    with pytest.raises(DecryptionFailedException):
        decrypt_credentials(envelope, key=ANOTHER_VALID_KEY)


def test_tampered_ciphertext_fails_safely():
    """Altering ciphertext characters must trigger DecryptionFailedException (HMAC verification failure)."""
    creds = {"secret": "my_val"}
    envelope = encrypt_credentials(creds, key=VALID_TEST_KEY)

    # Tamper with the ciphertext
    original_ct = envelope["ciphertext"]
    tampered_ct = original_ct[:-4] + "AAAA"
    tampered_envelope = {
        "version": 1,
        "algorithm": "fernet",
        "ciphertext": tampered_ct,
    }

    with pytest.raises(DecryptionFailedException):
        decrypt_credentials(tampered_envelope, key=VALID_TEST_KEY)


def test_malformed_envelope_rejected_safely():
    """Unrecognized envelope structures or legacy non-envelope formats must be rejected safely."""
    bad_envelopes = [
        {"version": 2, "algorithm": "fernet", "ciphertext": "abc"},
        {"version": 1, "algorithm": "aes-gcm", "ciphertext": "abc"},
        {"version": 1, "algorithm": "fernet"},  # missing ciphertext
        {"version": 1, "algorithm": "fernet", "ciphertext": ""},
        {"api_key": "plaintext_legacy"},  # legacy unencrypted dictionary
        "not_a_dict",
        12345,
    ]

    for bad_env in bad_envelopes:
        with pytest.raises(DecryptionFailedException):
            decrypt_credentials(bad_env, key=VALID_TEST_KEY)


def test_has_configured_credentials():
    """Verify boolean detection of active credentials across empty and populated payloads."""
    assert has_configured_credentials(None) is False
    assert has_configured_credentials({}) is False
    assert has_configured_credentials([]) is False

    valid_env = encrypt_credentials({"api_key": "secret"}, key=VALID_TEST_KEY)
    assert has_configured_credentials(valid_env) is True

    # Legacy raw dict without ciphertext
    assert has_configured_credentials({"raw_secret": "val"}) is True
