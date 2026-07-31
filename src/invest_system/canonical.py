"""Deterministic JSON primitives used by InvestSystem-owned contracts.

This module intentionally implements only the repository's narrow canonical
JSON profile: UTF-8, lexicographically sorted object keys, compact separators,
and no floating-point values.  It is not an implementation of RFC 8785.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from hashlib import sha256
from types import MappingProxyType
from typing import Any

type JsonValue = (
    None | bool | int | str | datetime | tuple[JsonValue, ...] | Mapping[str, JsonValue]
)


class CanonicalJsonError(ValueError):
    """Raised when a value is outside the InvestSystem JSON profile."""


def normalize_utc(value: datetime, *, field_name: str = "timestamp") -> datetime:
    """Validate an aware UTC datetime and normalize its tzinfo to ``timezone.utc``."""

    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware UTC")
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must be UTC, not a non-zero offset")
    return value.astimezone(UTC)


def format_utc(value: datetime) -> str:
    """Serialize an aware UTC datetime with six fractional digits and ``Z``."""

    normalized = normalize_utc(value)
    return normalized.isoformat(timespec="microseconds").replace("+00:00", "Z")


def freeze_json(value: Any, *, path: str = "$") -> JsonValue:
    """Deep-freeze a JSON-like value while rejecting floats and invalid keys.

    Lists become tuples and mappings become read-only mapping proxies.  Aware
    UTC datetimes are retained in normalized form and serialize as ``Z``.
    """

    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, float):
        # This rejects finite floats, infinities, and NaN alike.  Exact decimal
        # business values must be represented by a contract-defined string or
        # scaled integer instead of an implicit binary float.
        raise CanonicalJsonError(f"floating-point values are forbidden at {path}")
    if isinstance(value, int):
        return value
    if isinstance(value, datetime):
        return normalize_utc(value, field_name=path)
    if isinstance(value, Enum):
        return freeze_json(value.value, path=path)
    if isinstance(value, Mapping):
        frozen: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonicalJsonError(f"object key at {path} must be a string")
            frozen[key] = freeze_json(item, path=f"{path}.{key}")
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(freeze_json(item, path=f"{path}[{index}]") for index, item in enumerate(value))
    raise CanonicalJsonError(f"unsupported canonical JSON value at {path}: {type(value).__name__}")


def to_json_value(value: Any, *, path: str = "$") -> Any:
    """Project supported models and values into JSON-native Python objects."""

    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, float):
        raise CanonicalJsonError(f"floating-point values are forbidden at {path}")
    if isinstance(value, int):
        return value
    if isinstance(value, datetime):
        return format_utc(value)
    if isinstance(value, Enum):
        return to_json_value(value.value, path=path)
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: to_json_value(getattr(value, field.name), path=f"{path}.{field.name}")
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        projected: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonicalJsonError(f"object key at {path} must be a string")
            projected[key] = to_json_value(item, path=f"{path}.{key}")
        return projected
    if isinstance(value, (list, tuple)):
        return [to_json_value(item, path=f"{path}[{index}]") for index, item in enumerate(value)]
    raise CanonicalJsonError(f"unsupported canonical JSON value at {path}: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    """Return canonical JSON text for exactly the value supplied by the caller."""

    return json.dumps(
        to_json_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def canonical_json_bytes(value: Any) -> bytes:
    """Return the canonical JSON encoded as UTF-8."""

    return canonical_json(value).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    """Hash exactly the supplied value and return lowercase SHA-256 hex.

    Self-referential fields are never removed implicitly.  To calculate a
    receipt or replay identity, the caller must explicitly pass a payload that
    omits the corresponding hash field.
    """

    return sha256(canonical_json_bytes(value)).hexdigest()
