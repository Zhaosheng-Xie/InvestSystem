from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any, cast

import pytest

from invest_system import DeliveryTransport
from invest_system.integrations.investment_research_kb import (
    KBTransportCapability,
    KBTransportNotSupportedError,
    TransportSupportStatus,
    kb_transport_capabilities,
    require_supported_kb_transport,
)


def test_every_approved_kb_transport_fails_closed_before_io() -> None:
    capabilities = kb_transport_capabilities()

    assert isinstance(capabilities, tuple)
    assert tuple(item.transport for item in capabilities) == tuple(DeliveryTransport)
    for capability in capabilities:
        assert capability.status is TransportSupportStatus.NOT_SUPPORTED
        assert capability.blocker
        assert capability.planned_stage == "Stage 3"
        with pytest.raises(KBTransportNotSupportedError) as caught:
            require_supported_kb_transport(capability.transport)
        assert caught.value.transport is capability.transport
        assert caught.value.blocker == capability.blocker
        assert caught.value.planned_stage == capability.planned_stage


def test_transport_capabilities_are_strict_and_immutable() -> None:
    capability = kb_transport_capabilities()[0]

    with pytest.raises(FrozenInstanceError):
        cast(Any, capability).blocker = "changed"
    with pytest.raises(TypeError, match="DeliveryTransport"):
        require_supported_kb_transport(cast(DeliveryTransport, "read_only_http_api"))
    with pytest.raises(ValueError, match="unsupported transport must have a blocker"):
        KBTransportCapability(
            transport=DeliveryTransport.READ_ONLY_HTTP_API,
            status=TransportSupportStatus.NOT_SUPPORTED,
            blocker=None,
            planned_stage="Stage 3",
        )


def test_support_matrix_matches_the_executable_transport_boundary(
    repository_root: Path,
) -> None:
    matrix_path = (
        repository_root
        / "contracts"
        / "providers"
        / "investment_research_kb"
        / "v1"
        / "support-matrix.json"
    )
    matrix = json.loads(matrix_path.read_bytes())
    entries = {
        DeliveryTransport.READ_ONLY_HTTP_API: matrix["capabilities"]["http_transport"],
        DeliveryTransport.IMMUTABLE_EXPORT: matrix["capabilities"]["immutable_export_transport"],
    }

    for capability in kb_transport_capabilities():
        entry = entries[capability.transport]
        assert entry == {
            "status": "not_implemented",
            "blocker": capability.blocker,
            "planned_stage": capability.planned_stage,
            "unsupported_behavior": "fail_closed_before_io",
        }
