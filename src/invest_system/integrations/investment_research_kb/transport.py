"""Fail-closed capability boundary for KB delivery transports.

Stage 2A deliberately does not guess an HTTP envelope or an immutable export
package format.  Both approved delivery surfaces remain unavailable until the
provider publishes a versioned public contract that InvestSystem can pin and
verify.  Callers can inspect this capability registry, but they cannot acquire
provider data through this module yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from invest_system.consumption import DeliveryTransport


class TransportSupportStatus(StrEnum):
    """Whether a pinned public contract permits a transport implementation."""

    SUPPORTED = "supported"
    NOT_SUPPORTED = "not_supported"


@dataclass(frozen=True, slots=True)
class KBTransportCapability:
    """Machine-readable support decision for one approved delivery surface."""

    transport: DeliveryTransport
    status: TransportSupportStatus
    blocker: str | None
    planned_stage: str

    def __post_init__(self) -> None:
        if not isinstance(self.transport, DeliveryTransport):
            raise TypeError("transport must be a DeliveryTransport")
        if not isinstance(self.status, TransportSupportStatus):
            raise TypeError("status must be a TransportSupportStatus")
        if not isinstance(self.planned_stage, str) or not self.planned_stage.strip():
            raise ValueError("planned_stage must be a non-empty string")
        if self.status is TransportSupportStatus.SUPPORTED:
            if self.blocker is not None:
                raise ValueError("a supported transport cannot have a blocker")
        elif not isinstance(self.blocker, str) or not self.blocker.strip():
            raise ValueError("an unsupported transport must have a blocker")


class KBTransportNotSupportedError(RuntimeError):
    """Raised before I/O when a delivery contract has not been pinned."""

    def __init__(self, capability: KBTransportCapability) -> None:
        if capability.status is not TransportSupportStatus.NOT_SUPPORTED:
            raise ValueError("capability must be not_supported")
        self.transport = capability.transport
        self.blocker = capability.blocker
        self.planned_stage = capability.planned_stage
        super().__init__(
            f"{capability.transport.value} is not supported: {capability.blocker} "
            f"(planned for {capability.planned_stage})"
        )


_TRANSPORT_CAPABILITIES: Final[tuple[KBTransportCapability, ...]] = (
    KBTransportCapability(
        transport=DeliveryTransport.READ_ONLY_HTTP_API,
        status=TransportSupportStatus.NOT_SUPPORTED,
        blocker="locked_public_http_envelope_or_openapi_contract_missing",
        planned_stage="Stage 3",
    ),
    KBTransportCapability(
        transport=DeliveryTransport.IMMUTABLE_EXPORT,
        status=TransportSupportStatus.NOT_SUPPORTED,
        blocker="locked_export_package_schema_lock_and_fixture_missing",
        planned_stage="Stage 3",
    ),
)


def kb_transport_capabilities() -> tuple[KBTransportCapability, ...]:
    """Return the immutable capability registry in stable enum order."""

    return _TRANSPORT_CAPABILITIES


def require_supported_kb_transport(
    transport: DeliveryTransport,
) -> KBTransportCapability:
    """Return support metadata or fail before any transport I/O is attempted."""

    if not isinstance(transport, DeliveryTransport):
        raise TypeError("transport must be a DeliveryTransport")
    capability = next(item for item in _TRANSPORT_CAPABILITIES if item.transport is transport)
    if capability.status is not TransportSupportStatus.SUPPORTED:
        raise KBTransportNotSupportedError(capability)
    return capability
