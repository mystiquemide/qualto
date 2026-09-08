from __future__ import annotations

from pathlib import Path

import pytest

from qualto.engine.receipts import ReceiptLog
from qualto.engine.session import (
    ClaimReplayError,
    Session,
    SessionBlockedError,
    SessionClosedError,
    SessionState,
)


def make_session(tmp_path: Path) -> Session:
    return Session("session-001", ReceiptLog(tmp_path / "receipts.jsonl"))


def active_session(tmp_path: Path) -> Session:
    session = make_session(tmp_path)
    session.connect()
    session.activate()
    return session


def test_session_state_lifecycle(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    assert session.state is SessionState.CREATED
    session.connect()
    session.activate()
    session.block("test failure")
    assert session.state is SessionState.BLOCKED
    session.recover()
    session.close()
    assert session.state is SessionState.CLOSED


def test_blocked_session_rejects_writes(tmp_path: Path) -> None:
    session = active_session(tmp_path)
    session.block("readback failed")

    with pytest.raises(SessionBlockedError, match="readback failed"):
        session.assert_can_write()


def test_claim_ids_are_single_use(tmp_path: Path) -> None:
    session = active_session(tmp_path)
    session.reserve_claim_id("qualto-claim-abcdefghijkl")

    with pytest.raises(ClaimReplayError):
        session.reserve_claim_id("qualto-claim-abcdefghijkl")


def test_closed_session_rejects_changes(tmp_path: Path) -> None:
    session = active_session(tmp_path)
    session.close()

    with pytest.raises(SessionClosedError):
        session.record({"event": "late"})
