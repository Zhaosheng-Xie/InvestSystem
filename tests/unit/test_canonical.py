from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from hashlib import sha256

import pytest

from invest_system import (
    CanonicalJsonError,
    canonical_json,
    canonical_json_bytes,
    canonical_sha256,
    format_utc,
    freeze_json,
    normalize_utc,
)


def test_canonical_json_is_sorted_compact_utf8_and_order_independent() -> None:
    first = {"z": [1, {"b": "汉字", "a": True}], "a": None}
    second = {"a": None, "z": [1, {"a": True, "b": "汉字"}]}
    expected = '{"a":null,"z":[1,{"a":true,"b":"汉字"}]}'

    assert canonical_json(first) == expected
    assert canonical_json(second) == expected
    assert canonical_json_bytes(first) == expected.encode("utf-8")
    assert canonical_sha256(first) == sha256(expected.encode("utf-8")).hexdigest()


@pytest.mark.parametrize(
    "floating_value",
    [0.0, -0.0, float("nan"), float("inf"), float("-inf")],
    ids=["zero", "negative-zero", "nan", "positive-infinity", "negative-infinity"],
)
@pytest.mark.parametrize("container", ["direct", "mapping", "list", "deeply-nested"])
def test_canonical_profile_rejects_every_float_recursively(
    floating_value: float,
    container: str,
) -> None:
    values = {
        "direct": floating_value,
        "mapping": {"value": floating_value},
        "list": [floating_value],
        "deeply-nested": {"items": [{"value": floating_value}]},
    }

    with pytest.raises(CanonicalJsonError, match="floating-point values are forbidden"):
        canonical_json(values[container])


@pytest.mark.parametrize("value", [{1: "not-a-string-key"}, {"value": b"bytes"}, {"value": {1}}])
def test_canonical_profile_rejects_unsupported_values(value: object) -> None:
    with pytest.raises(CanonicalJsonError):
        canonical_json(value)


def test_freeze_json_deeply_detaches_mutable_input() -> None:
    source = {"facts": [{"value": 1}]}
    frozen = freeze_json(source)

    source["facts"][0]["value"] = 2
    source["facts"].append({"value": 3})

    assert canonical_json(frozen) == '{"facts":[{"value":1}]}'
    with pytest.raises(TypeError):
        frozen["new"] = "forbidden"  # type: ignore[index]


def test_utc_format_is_fixed_and_naive_or_nonzero_offsets_are_rejected() -> None:
    utc_value = datetime(2026, 7, 30, 8, 9, 10, 123, tzinfo=UTC)
    assert normalize_utc(utc_value).tzinfo is UTC
    assert format_utc(utc_value) == "2026-07-30T08:09:10.000123Z"

    with pytest.raises(ValueError, match="timezone-aware UTC"):
        normalize_utc(datetime(2026, 7, 30, 8, 9, 10))

    nonzero_offset = datetime(
        2026,
        7,
        30,
        16,
        9,
        10,
        tzinfo=timezone(timedelta(hours=8)),
    )
    with pytest.raises(ValueError, match="non-zero offset"):
        normalize_utc(nonzero_offset)


def test_hashes_exact_payload_and_never_implicitly_removes_self_hash_fields() -> None:
    identity_payload = {"decision_id": "synthetic_decision_stage1_001"}
    payload_with_hash_field = {
        **identity_payload,
        "replay_hash": {"algorithm": "sha256", "value": "0" * 64},
    }

    assert canonical_sha256(payload_with_hash_field) != canonical_sha256(identity_payload)
