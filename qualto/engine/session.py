"""Session state machine and session-wide write enforcement."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .receipts import ReceiptLog


class SessionState(StrEnum):
    CREATED = "CREATED"
    CONNECTED = "CONNECTED"
    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"
    CLOSED = "CLOSED"
    ERROR = "ERROR"


class SessionBlockedError(RuntimeError):
    """A session cannot perform a write after an unresolved failure."""


class SessionClosedError(RuntimeError):
    """A closed session cannot be changed."""


class ClaimReplayError(RuntimeError):
    """A claim ID was already used in this session."""


@dataclass
class Session:
    """Rebuildable session state backed by receipts."""

    session_id: str
    receipts: ReceiptLog
    state: SessionState = SessionState.CREATED
    block_reason: str | None = None
    _used_claim_ids: set[str] = field(default_factory=set, repr=False)

    def connect(self) -> None:
        self._require_not_closed()
        if self.state is not SessionState.CREATED:
            raise RuntimeError("session is already connected or finished")
        self.state = SessionState.CONNECTED

    def activate(self) -> None:
        self._require_not_closed()
        if self.state not in {SessionState.CONNECTED, SessionState.BLOCKED}:
            raise RuntimeError("session cannot become active from its current state")
        self.state = SessionState.ACTIVE
        self.block_reason = None

    def assert_can_write(self) -> None:
        self._require_not_closed()
        if self.state is SessionState.BLOCKED:
            raise SessionBlockedError(self.block_reason or "session is blocked")
        if self.state is not SessionState.ACTIVE:
            raise RuntimeError("session is not active")

    def reserve_claim_id(self, claim_id: str) -> None:
        self.assert_can_write()
        if claim_id in self._used_claim_ids:
            raise ClaimReplayError("claim ID was already used in this session")
        self._used_claim_ids.add(claim_id)

    def block(self, reason: str, *, receipt: dict[str, Any] | None = None) -> None:
        self._require_not_closed()
        self.state = SessionState.BLOCKED
        self.block_reason = reason
        if receipt is not None:
            self.receipts.append(receipt)

    def recover(self) -> None:
        if self.state is not SessionState.BLOCKED:
            raise RuntimeError("session is not blocked")
        self.activate()

    def close(self, *, receipt: dict[str, Any] | None = None) -> None:
        self._require_not_closed()
        self.state = SessionState.CLOSED
        if receipt is not None:
            self.receipts.append(receipt)

    def record(self, event: dict[str, Any]) -> None:
        self._require_not_closed()
        self.receipts.append(event)

    def _require_not_closed(self) -> None:
        if self.state is SessionState.CLOSED:
            raise SessionClosedError("session is closed")
