"""Pydantic request and response schemas for third-party integrations."""

from datetime import datetime
from typing import Any, Dict, Optional, Set
from pydantic import BaseModel, ConfigDict, Field, field_validator

SUPPORTED_PROVIDERS: Set[str] = {
    "google_calendar",
    "sendgrid",
    "resend",
    "slack",
    "zapier",
    "webhook",
}

DISALLOWED_CONFIG_SECRET_SUBSTRINGS = (
    "secret",
    "password",
    "api_key",
    "apikey",
    "private_key",
    "auth_token",
    "access_token",
    "refresh_token",
)


def _scan_no_secrets_recursive(data: Any, path: str = "config") -> None:
    """Recursively inspect nested dictionaries and lists for disallowed secret keys."""
    if isinstance(data, dict):
        for key, value in data.items():
            k_clean = str(key).lower().replace("-", "_").strip()
            if any(sub in k_clean for sub in DISALLOWED_CONFIG_SECRET_SUBSTRINGS) or k_clean == "token":
                full_path = f"{path}.{key}" if path else str(key)
                raise ValueError(
                    f"Config key '{full_path}' appears to contain sensitive credential data. "
                    "Secrets must be provided in the 'credentials' field, not in plaintext 'config'."
                )
            _scan_no_secrets_recursive(value, path=f"{path}.{key}")
    elif isinstance(data, list):
        for idx, item in enumerate(data):
            _scan_no_secrets_recursive(item, path=f"{path}[{idx}]")


class IntegrationUpsertRequest(BaseModel):
    """Payload to create or update an integration configuration."""

    provider: Optional[str] = Field(
        None,
        description="Optional provider name; if omitted, taken from the URL path parameter.",
    )
    is_active: Optional[bool] = Field(
        False,
        description="Whether the integration is actively enabled.",
    )
    config: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Non-sensitive configuration parameters (e.g. endpoints, channel names, calendar IDs).",
    )
    credentials: Optional[Dict[str, Any]] = Field(
        None,
        description="Write-only sensitive credentials dictionary. Omit to preserve existing credentials; pass {} to clear.",
    )

    @field_validator("config")
    @classmethod
    def validate_config_no_secrets(cls, v: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not v:
            return {}
        _scan_no_secrets_recursive(v, path="config")
        return v

    @field_validator("provider")
    @classmethod
    def validate_provider_field(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        clean_v = v.strip().lower()
        if clean_v not in SUPPORTED_PROVIDERS:
            raise ValueError(
                f"Unsupported integration provider '{v}'. Supported providers: {', '.join(sorted(SUPPORTED_PROVIDERS))}."
            )
        return clean_v


class IntegrationResponse(BaseModel):
    """Public, safe representation of an organization's integration configuration."""

    id: str
    provider: str
    is_active: bool
    config: Dict[str, Any]
    has_credentials: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
