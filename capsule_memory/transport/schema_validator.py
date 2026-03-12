from __future__ import annotations
from typing import Any
from capsule_memory.models.capsule import (
    _PROTO_SCHEMA_TAG,
    _K,
    _PKG_NAME,
    _PKG_URL,
)

_VALID_SCHEMA_PREFIX = "capsule-schema/1.0+"
_VALID_SCHEMA_VERSION = f"{_VALID_SCHEMA_PREFIX}{_PROTO_SCHEMA_TAG}"


def validate_capsule(data: dict[str, Any]) -> tuple[bool, list[str]]:
    """
    Validate whether a dict conforms to the CapsuleMemory capsule format spec.

    In addition to standard field checks, also verifies:
    - schema_version must equal _VALID_SCHEMA_VERSION
    - integrity.checksum if non-empty must be a 64-char hex string (HMAC-SHA256)
    - capsule_id must start with "cap_"

    Args:
        data: The capsule dict to validate.

    Returns:
        (is_valid, error_messages). is_valid=True when error_messages is empty.
    """
    errors: list[str] = []

    required = ["capsule_id", "capsule_type", "schema_version", "identity", "payload"]
    for field in required:
        if field not in data:
            errors.append(f"Missing required field: '{field}'")

    if "capsule_id" in data and not str(data["capsule_id"]).startswith("cap_"):
        errors.append(f"capsule_id must start with 'cap_', got: {data['capsule_id']!r}")

    sv = data.get("schema_version", "")
    if sv != _VALID_SCHEMA_VERSION:
        if sv.startswith(_VALID_SCHEMA_PREFIX):
            errors.append(
                f"schema_version mismatch: expected '{_VALID_SCHEMA_VERSION}', got '{sv}'."
            )
        else:
            errors.append(
                f"Invalid schema_version: '{sv}'. "
                f"Expected: '{_VALID_SCHEMA_VERSION}'"
            )

    valid_types = {"memory", "skill", "hybrid", "context"}
    if "capsule_type" in data and data["capsule_type"] not in valid_types:
        errors.append(f"Invalid capsule_type: '{data['capsule_type']}'. Valid: {valid_types}")

    integrity = data.get("integrity", {})
    checksum = integrity.get("checksum", "")
    if checksum and (len(checksum) != 64 or not all(c in "0123456789abcdef" for c in checksum)):
        errors.append("integrity.checksum must be a 64-char hex string (HMAC-SHA256)")

    identity = data.get("identity", {})
    for sub in ["user_id", "session_id"]:
        if not identity.get(sub):
            errors.append(f"identity.{sub} is required and must be non-empty")

    return (len(errors) == 0), errors


def validate_universal_memory(data: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate whether data is a valid universal memory format."""
    errors: list[str] = []
    if data.get("schema") != "universal-memory/1.0":
        errors.append(f"schema must be 'universal-memory/1.0', got: {data.get('schema')!r}")
    if "prompt_injection" not in data:
        errors.append("Missing required field: 'prompt_injection'")
    if not isinstance(data.get("facts", []), list):
        errors.append("'facts' must be a list")
    if not isinstance(data.get("skills", []), list):
        errors.append("'skills' must be a list")
    return (len(errors) == 0), errors


def verify_checksum(capsule_dict: dict[str, Any]) -> bool:
    """Verify integrity of a deserialized capsule dict."""
    import hmac
    import json

    stored = capsule_dict.get("integrity", {}).get("checksum", "")
    status = capsule_dict.get("lifecycle", {}).get("status", "draft")
    if not stored:
        return status == "draft"

    metadata = capsule_dict.get("metadata", {})
    signed = {
        "payload": capsule_dict.get("payload", {}),
        "capsule_created_by": metadata.get("capsule_created_by", _PKG_NAME),
        "capsule_project_url": metadata.get("capsule_project_url", _PKG_URL),
    }
    data_str = json.dumps(signed, sort_keys=True, ensure_ascii=False, default=str)
    expected = hmac.new(_K, data_str.encode(), "sha256").hexdigest()
    return hmac.compare_digest(stored, expected)
