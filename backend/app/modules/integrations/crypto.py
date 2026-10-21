"""Symmetric encryption and decryption utilities for integration credentials.

Secures third-party API credentials, webhook signing secrets, and OAuth tokens
at rest using Fernet (AES-128-CBC + HMAC-SHA256 authenticated encryption).
Credentials are encapsulated in a versioned storage envelope before persistence.
"""

import json
from typing import Any, Dict, Optional
from cryptography.fernet import Fernet, InvalidToken
from fastapi import status

from app.core.config import settings
from app.core.exceptions import AppException
from app.core.logging import logger


class EncryptionKeyMissingException(AppException):
    """Raised when encryption or decryption is attempted without a configured key."""

    def __init__(self, message: str = "Integration encryption key is not configured"):
        super().__init__(
            message=message,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="ENCRYPTION_KEY_MISSING",
        )


class EncryptionKeyInvalidException(AppException):
    """Raised when the configured encryption key is not a valid 32-byte Fernet key."""

    def __init__(self, message: str = "Integration encryption key is invalid"):
        super().__init__(
            message=message,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="ENCRYPTION_KEY_INVALID",
        )


class DecryptionFailedException(AppException):
    """Raised when an encrypted credentials envelope cannot be decrypted or parsed."""

    def __init__(self, message: str = "Failed to decrypt integration credentials"):
        super().__init__(
            message=message,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="DECRYPTION_FAILED",
        )


def _get_fernet(key: Optional[str] = None) -> Fernet:
    """Validate and instantiate a Fernet cipher instance safely.

    If key is omitted, resolves from settings.INTEGRATION_ENCRYPTION_KEY.
    Raises EncryptionKeyMissingException if key is absent or blank.
    Raises EncryptionKeyInvalidException if key cannot initialize Fernet.
    """
    configured_key = key if key is not None else settings.INTEGRATION_ENCRYPTION_KEY

    if not configured_key or not str(configured_key).strip():
        raise EncryptionKeyMissingException(
            "Integration encryption key is missing. Set INTEGRATION_ENCRYPTION_KEY in your environment."
        )

    try:
        key_bytes = str(configured_key).strip().encode("utf-8")
        return Fernet(key_bytes)
    except Exception:
        raise EncryptionKeyInvalidException(
            "Integration encryption key is invalid. Key must be a 32-byte url-safe base64-encoded string."
        )


def encrypt_credentials(
    credentials: Optional[Dict[str, Any]],
    key: Optional[str] = None,
) -> Dict[str, Any]:
    """Encrypt a credentials dictionary into a versioned storage envelope.

    Empty credentials return an empty dict {} without requiring an encryption key.
    Non-empty credentials require a valid Fernet key. Never persists plaintext.
    """
    if not credentials:
        return {}

    if not isinstance(credentials, dict):
        raise DecryptionFailedException("Credentials payload must be a JSON object dictionary.")

    fernet = _get_fernet(key)

    try:
        serialized = json.dumps(credentials, sort_keys=True).encode("utf-8")
        ciphertext = fernet.encrypt(serialized).decode("utf-8")
        return {
            "version": 1,
            "algorithm": "fernet",
            "ciphertext": ciphertext,
        }
    except AppException:
        raise
    except Exception:
        logger.error("Failed to encrypt credentials payload.")
        raise AppException(
            message="An unexpected error occurred while encrypting credentials.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="ENCRYPTION_FAILED",
        )


def decrypt_credentials(
    envelope: Optional[Dict[str, Any]],
    key: Optional[str] = None,
) -> Dict[str, Any]:
    """Decrypt a versioned storage envelope back to a plaintext credentials dict.

    Rejects malformed or legacy plaintext envelopes safely without logging secrets.
    """
    if not envelope:
        return {}

    if not isinstance(envelope, dict):
        raise DecryptionFailedException("Malformed credentials storage: expected envelope dictionary.")

    # Check for recognized versioned Fernet envelope
    version = envelope.get("version")
    algo = envelope.get("algorithm")
    ciphertext = envelope.get("ciphertext")

    if version != 1 or algo != "fernet" or not ciphertext or not isinstance(ciphertext, str):
        logger.error("Encountered unrecognized or malformed credentials envelope format.")
        raise DecryptionFailedException(
            "Unsupported or malformed credentials envelope format. Cannot decrypt safely."
        )

    fernet = _get_fernet(key)

    try:
        decrypted_bytes = fernet.decrypt(ciphertext.encode("utf-8"))
        data = json.loads(decrypted_bytes.decode("utf-8"))
        if not isinstance(data, dict):
            raise DecryptionFailedException("Decrypted credentials content is not a dictionary.")
        return data
    except InvalidToken:
        logger.error("Fernet decryption failed: invalid token, corrupt ciphertext, or wrong key.")
        raise DecryptionFailedException("Failed to decrypt integration credentials: token or key invalid.")
    except json.JSONDecodeError:
        logger.error("Decrypted payload could not be parsed as valid JSON.")
        raise DecryptionFailedException("Decrypted credentials content is not valid JSON.")
    except AppException:
        raise
    except Exception:
        logger.error("Failed to decrypt credentials envelope.")
        raise DecryptionFailedException("Failed to decrypt integration credentials.")


def has_configured_credentials(envelope: Any) -> bool:
    """Determine whether stored credentials represent non-empty active credentials."""
    if not envelope or not isinstance(envelope, dict):
        return False

    if envelope.get("version") == 1 and envelope.get("algorithm") == "fernet" and envelope.get("ciphertext"):
        return True

    # Legacy or non-empty non-envelope dictionary
    if len(envelope) > 0 and not envelope.get("ciphertext"):
        return True

    return False
