"""Backend session flows for gateway failures and recovery."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .attest import Attestation, AttestationEngine, Verdict
from .claim import Claim
from .session import Session, SessionState


class GatewayLifecycle(Protocol):
    @property
    def connected(self) -> bool:
        """Whether gateway calls are enabled."""

    def disconnect(self) -> None:
        """Disable gateway calls."""

    def reconnect(self) -> None:
        """Restore gateway calls."""


@dataclass(frozen=True, slots=True)
class NegativePathResult:
    claim: Claim
    attestation: Attestation
    blocked_state: SessionState
    recovered_state: SessionState
    gateway_disconnected: bool

    def to_mapping(self) -> dict[str, Any]:
        return {
            "claim": self.claim.to_mapping(),
            "attestation": self.attestation.to_mapping(),
            "negativePath": {
                "gatewayDisconnected": self.gateway_disconnected,
                "writeBlocked": self.blocked_state is SessionState.BLOCKED,
                "blockedState": self.blocked_state.value,
                "recoveredState": self.recovered_state.value,
                "recovered": self.recovered_state is SessionState.ACTIVE,
            },
        }


class NegativePathRunner:
    """Run one deliberate disconnect-before-placement flow and recover."""

    def __init__(
        self,
        gateway: GatewayLifecycle,
        session: Session,
        engine: AttestationEngine,
    ) -> None:
        self.gateway = gateway
        self.session = session
        self.engine = engine

    def run(self, claim: Claim) -> NegativePathResult:
        self.gateway.disconnect()
        disconnected = not self.gateway.connected
        attestation = self.engine.place_and_attest(claim)
        blocked_state = self.session.state
        if (
            attestation.verdict is not Verdict.UNPROVED
            or blocked_state is not SessionState.BLOCKED
        ):
            raise RuntimeError(
                "disconnected gateway did not produce a blocked UNPROVED state"
            )
        self.gateway.reconnect()
        self.session.recover()
        self.session.record(
            {
                "event": "gateway_recovery",
                "claimId": claim.claim_id,
                "outcome": "recovered",
                "reason": "gateway reconnected and session recovered",
            }
        )
        return NegativePathResult(
            claim=claim,
            attestation=attestation,
            blocked_state=blocked_state,
            recovered_state=self.session.state,
            gateway_disconnected=disconnected,
        )
