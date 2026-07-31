"""Canonical JSON primitives for the pinned InvestmentResearchKB v1 contract.

This module implements the provider-owned ``irkb-jsonl-v1`` profile.  It is
deliberately separate from :mod:`invest_system.canonical`: the provider profile
normalizes Unicode to NFC and permits finite JSON floating-point numbers,
whereas InvestSystem-owned identities use a narrower no-float profile.
"""

from __future__ import annotations

import json
import math
import unicodedata
from collections.abc import Iterable, Sequence
from hashlib import sha256
from typing import cast

CANONICALIZATION_PROFILE = "irkb-jsonl-v1"

type ProviderJsonValue = (
    None | bool | int | float | str | list[ProviderJsonValue] | dict[str, ProviderJsonValue]
)


class ProviderCanonicalError(ValueError):
    """Raised when a value cannot be represented by ``irkb-jsonl-v1``."""


def _nfc(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def _normalize_json(
    value: object,
    *,
    path: str,
    active_containers: set[int],
) -> ProviderJsonValue:
    value_type = type(value)
    if value is None:
        return None
    if value_type is bool:
        return cast(bool, value)
    if value_type is int:
        return cast(int, value)
    if value_type is float:
        number = cast(float, value)
        if not math.isfinite(number):
            raise ProviderCanonicalError(f"non-finite JSON number at {path}")
        return number
    if value_type is str:
        return _nfc(cast(str, value))

    if value_type is list:
        array_items = cast(list[object], value)
        identity = id(value)
        if identity in active_containers:
            raise ProviderCanonicalError(f"cyclic JSON array at {path}")
        active_containers.add(identity)
        try:
            return [
                _normalize_json(
                    item,
                    path=f"{path}[{index}]",
                    active_containers=active_containers,
                )
                for index, item in enumerate(array_items)
            ]
        finally:
            active_containers.remove(identity)

    if value_type is dict:
        object_items = cast(dict[object, object], value)
        identity = id(value)
        if identity in active_containers:
            raise ProviderCanonicalError(f"cyclic JSON object at {path}")
        active_containers.add(identity)
        try:
            normalized: dict[str, ProviderJsonValue] = {}
            original_keys: dict[str, str] = {}
            for key, item in object_items.items():
                if type(key) is not str:
                    raise ProviderCanonicalError(f"JSON object key at {path} must be a string")
                normalized_key = _nfc(key)
                if normalized_key in normalized:
                    first = original_keys[normalized_key]
                    raise ProviderCanonicalError(
                        f"NFC key collision at {path}: {first!r} and {key!r}"
                    )
                original_keys[normalized_key] = key
                normalized[normalized_key] = _normalize_json(
                    item,
                    path=f"{path}.{normalized_key}",
                    active_containers=active_containers,
                )
            return normalized
        finally:
            active_containers.remove(identity)

    raise ProviderCanonicalError(f"unsupported JSON value at {path}: {type(value).__name__}")


def normalize_json_nfc(value: object) -> ProviderJsonValue:
    """Return a detached JSON value with every key and string normalized to NFC."""

    return _normalize_json(value, path="$", active_containers=set())


def _encode_normalized(value: ProviderJsonValue) -> bytes:
    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        return text.encode("utf-8")
    except (UnicodeEncodeError, ValueError) as error:
        raise ProviderCanonicalError("value is not valid canonical UTF-8 JSON") from error


def canonical_json_bytes(value: object) -> bytes:
    """Serialize one value as canonical UTF-8 JSON without a trailing newline."""

    return _encode_normalized(normalize_json_nfc(value))


def canonical_jsonl_bytes(
    records: Iterable[object],
    *,
    sort_keys: Sequence[str],
) -> bytes:
    """Sort and serialize JSON objects as canonical JSONL with a final LF.

    Sort-key values must be strings.  Both declared key names and record values
    participate in NFC normalization before ordering.
    """

    normalized_sort_keys: list[str] = []
    seen_sort_keys: dict[str, str] = {}
    for key in sort_keys:
        if type(key) is not str:
            raise ProviderCanonicalError("JSONL sort keys must be strings")
        normalized_key = _nfc(key)
        if normalized_key in seen_sort_keys:
            raise ProviderCanonicalError(
                f"NFC sort-key collision: {seen_sort_keys[normalized_key]!r} and {key!r}"
            )
        seen_sort_keys[normalized_key] = key
        normalized_sort_keys.append(normalized_key)

    normalized_records: list[dict[str, ProviderJsonValue]] = []
    for index, record in enumerate(records):
        normalized = normalize_json_nfc(record)
        if not isinstance(normalized, dict):
            raise ProviderCanonicalError(f"JSONL record {index} must be an object")
        for key in normalized_sort_keys:
            if key not in normalized:
                raise ProviderCanonicalError(f"JSONL record {index} is missing sort key {key!r}")
            if type(normalized[key]) is not str:
                raise ProviderCanonicalError(
                    f"JSONL record {index} sort key {key!r} must be a string"
                )
        normalized_records.append(normalized)

    normalized_records.sort(key=lambda record: tuple(record[key] for key in normalized_sort_keys))
    return b"".join(_encode_normalized(record) + b"\n" for record in normalized_records)


def manifest_sha256(manifest: object) -> str:
    """Hash a Manifest after omitting its top-level ``manifest_hash`` field."""

    normalized = normalize_json_nfc(manifest)
    if not isinstance(normalized, dict):
        raise ProviderCanonicalError("manifest must be a JSON object")
    unsigned = {key: value for key, value in normalized.items() if key != "manifest_hash"}
    return sha256(_encode_normalized(unsigned)).hexdigest()


def sealed_manifest_bytes(manifest: object) -> bytes:
    """Serialize a complete Manifest with exactly one physical trailing LF."""

    normalized = normalize_json_nfc(manifest)
    if not isinstance(normalized, dict):
        raise ProviderCanonicalError("manifest must be a JSON object")
    return _encode_normalized(normalized) + b"\n"
