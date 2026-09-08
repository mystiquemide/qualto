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


def test_session_error_state_records_safe_failure(tmp_path: Path) -> None:
    session = active_session(tmp_path)

    session.error(
        "agent execution failed",
        receipt={"event": "session_error", "outcome": "error"},
    )

    assert session.state is SessionState.ERROR
    assert session.error_reason == "agent execution failed"
    assert session.block_reason is None
    assert session.receipts.entries()[-1]["event"] == "session_error"


def test_session_error_can_close_but_cannot_write_or_manage_orders(
    tmp_path: Path,
) -> None:
    session = active_session(tmp_path)
    session.error("provider failed")

    with pytest.raises(RuntimeError, match="not active"):
        session.assert_can_write()
    with pytest.raises(RuntimeError, match="manage an order"):
        session.assert_can_manage_order()

    session.close()
    assert session.state is SessionState.CLOSED
