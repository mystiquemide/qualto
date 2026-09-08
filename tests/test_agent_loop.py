from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

import pytest

from qualto.agent.loop import (
    AgentContextError,
    AgentLoop,
    AgentOutputError,
    HermesLLM,
    LLMProviderError,
)
from qualto.engine.claim import Claim


class FakeGateway:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def execute(
        self, tool_name: str, arguments: Mapping[str, Any] | None = None
    ) -> Any:
        self.calls.append((tool_name, dict(arguments or {})))
        if self.fail:
            raise RuntimeError("gateway unavailable")
        if tool_name == "spot.tickerPrice":
            return {"symbol": "BNBUSDT", "price": "752.85"}
        if tool_name == "spot.getAccount":
            return {"balances": [{"asset": "USDT", "free": "7.00000000"}]}
        raise AssertionError(tool_name)


class FakeLLM:
    def __init__(self, *responses: str) -> None:
        self.responses = list(responses)
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.responses.pop(0)


def claim_response(**overrides: Any) -> str:
    payload = {
        "claimId": "qualto-claim-abcdefghijkl",
        "mandate": "buy 5 USDT of BNB",
        "symbol": "BNBUSDT",
        "side": "BUY",
        "orderType": "LIMIT",
        "quantity": "0.006",
        "price": "700",
        "status": "NEW",
        "reason": "The live context supports a small bounded limit claim.",
    }
    payload.update(overrides)
    return json.dumps(payload)


def test_loop_fetches_live_context_and_returns_valid_claim(monkeypatch) -> None:
    gateway = FakeGateway()
    llm = FakeLLM(claim_response(claimId="qualto-claim-abcdefghijkl"))
    loop = AgentLoop(gateway, llm)
    monkeypatch.setattr(
        "qualto.agent.loop.mint_claim_id", lambda: "qualto-claim-abcdefghijkl"
    )

    claim = loop.generate_claim("buy 5 USDT of BNB")

    assert isinstance(claim, Claim)
    assert claim.quantity == Decimal("0.006")
    assert gateway.calls == [
        ("spot.tickerPrice", {"symbol": "BNBUSDT"}),
        ("spot.getAccount", {"omitZeroBalances": True}),
    ]
    assert "752.85" in llm.prompts[0]
    assert "7.00000000" in llm.prompts[0]


def test_loop_retries_malformed_output(monkeypatch) -> None:
    gateway = FakeGateway()
    llm = FakeLLM("not-json", claim_response(claimId="qualto-claim-abcdefghijkl"))
    loop = AgentLoop(gateway, llm)
    monkeypatch.setattr(
        "qualto.agent.loop.mint_claim_id", lambda: "qualto-claim-abcdefghijkl"
    )

    claim = loop.generate_claim("buy 5 USDT of BNB")

    assert claim.claim_id == "qualto-claim-abcdefghijkl"
    assert len(llm.prompts) == 2
    assert "failed strict validation" in llm.prompts[1]


def test_loop_fails_after_retry_budget(monkeypatch) -> None:
    gateway = FakeGateway()
    llm = FakeLLM("bad", "still bad", "bad again")
    loop = AgentLoop(gateway, llm, max_retries=2)
    monkeypatch.setattr(
        "qualto.agent.loop.mint_claim_id", lambda: "qualto-claim-abcdefghijkl"
    )

    with pytest.raises(AgentOutputError, match="bounded retries"):
        loop.generate_claim("buy 5 USDT of BNB")

    assert len(llm.prompts) == 3


def test_loop_rejects_model_claim_id_change(monkeypatch) -> None:
    gateway = FakeGateway()
    llm = FakeLLM(claim_response(claimId="qualto-claim-zzzzzzzzzzzz"))
    loop = AgentLoop(gateway, llm, max_retries=0)
    monkeypatch.setattr(
        "qualto.agent.loop.mint_claim_id", lambda: "qualto-claim-abcdefghijkl"
    )

    with pytest.raises(AgentOutputError, match="claim ID"):
        loop.generate_claim("buy 5 USDT of BNB")


def test_loop_rejects_incomplete_context() -> None:
    class IncompleteGateway(FakeGateway):
        def execute(
            self, tool_name: str, arguments: Mapping[str, Any] | None = None
        ) -> Any:
            if tool_name == "spot.tickerPrice":
                return {"symbol": "BNBUSDT"}
            return super().execute(tool_name, arguments)

    loop = AgentLoop(IncompleteGateway(), FakeLLM())

    with pytest.raises(AgentContextError, match="incomplete"):
        loop.generate_claim("buy 5 USDT of BNB")


def test_provider_error_is_not_retried_as_model_output() -> None:
    class FailingLLM:
        def complete(self, prompt: str) -> str:
            raise LLMProviderError("provider unavailable")

    loop = AgentLoop(FakeGateway(), FailingLLM())

    with pytest.raises(LLMProviderError):
        loop.generate_claim("buy 5 USDT of BNB")


def test_loop_enforces_an_overall_generation_deadline() -> None:
    llm = FakeLLM(claim_response(claimId="qualto-claim-abcdefghijkl"))
    loop = AgentLoop(FakeGateway(), llm, max_duration_seconds=1e-12)

    with pytest.raises(AgentOutputError, match="time budget"):
        loop.generate_claim("buy 5 USDT of BNB")

    assert llm.prompts == []


def test_hermes_prompt_is_sent_over_stdin_and_not_in_argv(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured.update(kwargs)
        return subprocess.CompletedProcess(command, 0, "response", "")

    monkeypatch.setattr("qualto.agent.loop.subprocess.run", fake_run)
    llm = HermesLLM(python_binary="hermes-python", timeout_seconds=90)

    assert llm.complete("private prompt", timeout_seconds=12.5) == "response"
    assert "private prompt" not in captured["command"]
    assert captured["input"] == "private prompt"
    assert captured["timeout"] == 12.5


def test_hermes_rejects_missing_secure_prompt_transport(monkeypatch) -> None:
    monkeypatch.setattr("qualto.agent.loop._hermes_python_binary", lambda _: None)

    with pytest.raises(LLMProviderError, match="secure Hermes prompt transport"):
        HermesLLM(binary="missing-hermes").complete("prompt")
