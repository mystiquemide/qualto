"""Harness-mediated, bounded LLM claim generation."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Protocol

from ..engine.claim import Claim, ClaimValidationError, mint_claim_id


class AgentContextError(RuntimeError):
    """Live context could not be read before the model was called."""


class AgentOutputError(RuntimeError):
    """The model did not produce a valid claim after bounded retries."""


class LLMProviderError(RuntimeError):
    """The configured LLM provider failed without exposing provider details."""


_HERMES_STDIN_LAUNCHER = (
    "import sys\n"
    "prompt = sys.stdin.read()\n"
    "sys.argv = ['hermes', '--toolsets', '', '--oneshot', prompt]\n"
    "from hermes_cli.main import main\n"
    "main()\n"
)


def _hermes_python_binary(binary: str) -> str | None:
    """Find the Python interpreter behind a Hermes console entry point."""

    resolved = shutil.which(binary)
    path = Path(resolved or binary)
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None

    first_line = text.splitlines()[0] if text.splitlines() else ""
    if first_line.startswith("#!"):
        shebang_interpreter = first_line[2:].strip().split()[0]
        if "python" in Path(shebang_interpreter).name:
            return shebang_interpreter

    target_match = re.search(r'exec\s+["\']([^"\']+)["\']', text)
    if target_match:
        target = Path(target_match.group(1))
        if target != path:
            target_interpreter = _hermes_python_binary(str(target))
            if target_interpreter is not None:
                return target_interpreter

    sibling = path.parent / "python"
    return str(sibling) if sibling.is_file() else None


class ContextGateway(Protocol):
    def execute(
        self, tool_name: str, arguments: Mapping[str, Any] | None = None
    ) -> Any:
        """Execute one allowlisted context operation."""


class LLMProvider(Protocol):
    def complete(self, prompt: str) -> str:
        """Return one model response as text."""


@dataclass(frozen=True, slots=True)
class MarketContext:
    symbol: str
    price: Decimal
    quote_asset: str
    quote_available: Decimal

    def to_mapping(self) -> dict[str, str]:
        return {
            "symbol": self.symbol,
            "price": format(self.price, "f"),
            "quoteAsset": self.quote_asset,
            "quoteAvailable": format(self.quote_available, "f"),
        }


class HermesLLM:
    """Call the authenticated Hermes provider without enabling arbitrary tools."""

    def __init__(
        self,
        *,
        binary: str | None = None,
        python_binary: str | None = None,
        timeout_seconds: float = 90.0,
    ) -> None:
        self.binary = binary or os.getenv("QUALTO_HERMES_BIN") or "hermes"
        self.python_binary = python_binary or os.getenv("QUALTO_HERMES_PYTHON")
        self.timeout_seconds = timeout_seconds

    def complete(self, prompt: str, *, timeout_seconds: float | None = None) -> str:
        timeout = (
            self.timeout_seconds
            if timeout_seconds is None
            else min(self.timeout_seconds, timeout_seconds)
        )
        if timeout <= 0:
            raise LLMProviderError("LLM provider time budget was exhausted")
        python_binary = self.python_binary or _hermes_python_binary(self.binary)
        if python_binary is None:
            raise LLMProviderError("secure Hermes prompt transport is unavailable")
        try:
            completed = subprocess.run(
                [python_binary, "-c", _HERMES_STDIN_LAUNCHER],
                check=False,
                capture_output=True,
                text=True,
                input=prompt,
                timeout=timeout,
                env={
                    key: value
                    for key, value in os.environ.items()
                    if key not in {"PYTHONHOME", "PYTHONPATH"}
                },
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise LLMProviderError("LLM provider is unavailable") from exc
        if completed.returncode != 0 or not completed.stdout.strip():
            raise LLMProviderError("LLM provider returned no usable response")
        return completed.stdout.strip()


def _decimal(value: Any, field_name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise AgentContextError(f"live context field {field_name} is invalid") from exc
    if not result.is_finite() or result < 0:
        raise AgentContextError(f"live context field {field_name} is invalid")
    return result


class AgentLoop:
    """Fetch live context, then request a strict claim with bounded retries."""

    def __init__(
        self,
        gateway: ContextGateway,
        llm: LLMProvider | None = None,
        *,
        quote_asset: str = "USDT",
        max_retries: int = 2,
        max_duration_seconds: float = 120.0,
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        if max_duration_seconds <= 0:
            raise ValueError("max_duration_seconds must be positive")
        self.gateway = gateway
        self.llm = llm or HermesLLM()
        self.quote_asset = quote_asset
        self.max_retries = max_retries
        self.max_duration_seconds = max_duration_seconds

    def generate_claim(self, mandate: str, *, symbol: str = "BNBUSDT") -> Claim:
        if not isinstance(mandate, str) or not 1 <= len(mandate.strip()) <= 500:
            raise ValueError("mandate must contain 1 to 500 characters")
        if (
            not isinstance(symbol, str)
            or not symbol.isalnum()
            or symbol.upper() != symbol
        ):
            raise ValueError("symbol must be uppercase alphanumeric text")
        deadline = time.monotonic() + self.max_duration_seconds
        self._ensure_deadline(deadline)
        context = self._read_context(symbol, deadline)
        claim_id = mint_claim_id()
        prompt = self._prompt(mandate, claim_id, context)
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self._complete(prompt, deadline)
                return self._parse_claim(response, claim_id, mandate, symbol)
            except (
                json.JSONDecodeError,
                ClaimValidationError,
                AgentOutputError,
            ) as exc:
                last_error = exc
                if attempt < self.max_retries:
                    self._ensure_deadline(deadline)
                    prompt = self._retry_prompt(mandate, claim_id, context)
                elif isinstance(exc, AgentOutputError):
                    raise
            except LLMProviderError:
                raise
        raise AgentOutputError(
            "LLM output was invalid after bounded retries"
        ) from last_error

    def _complete(self, prompt: str, deadline: float) -> str:
        remaining = self._remaining(deadline)
        if isinstance(self.llm, HermesLLM):
            return self.llm.complete(prompt, timeout_seconds=remaining)
        return self.llm.complete(prompt)

    def _read_context(self, symbol: str, deadline: float) -> MarketContext:
        try:
            self._ensure_deadline(deadline)
            price_payload = self.gateway.execute("spot.tickerPrice", {"symbol": symbol})
            self._ensure_deadline(deadline)
            account_payload = self.gateway.execute(
                "spot.getAccount", {"omitZeroBalances": True}
            )
            self._ensure_deadline(deadline)
            price = _decimal(price_payload["price"], "price")
            if price <= 0:
                raise AgentContextError("live context price must be greater than zero")
            balances = account_payload.get("balances", [])
            balance = next(
                item for item in balances if item.get("asset") == self.quote_asset
            )
            available = _decimal(balance.get("free"), "quoteAvailable")
        except AgentContextError:
            raise
        except (KeyError, TypeError, StopIteration, AttributeError) as exc:
            raise AgentContextError("live Binance context is incomplete") from exc
        return MarketContext(symbol, price, self.quote_asset, available)

    @staticmethod
    def _remaining(deadline: float) -> float:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AgentOutputError("agent generation exceeded its time budget")
        return remaining

    @classmethod
    def _ensure_deadline(cls, deadline: float) -> None:
        cls._remaining(deadline)

    @staticmethod
    def _prompt(mandate: str, claim_id: str, context: MarketContext) -> str:
        return (
            "You are the claim proposer inside Qualto. Return exactly one JSON object and no markdown. "
            "The harness, not you, places orders. Do not call tools. Use only the exact schema and values "
            "required below. The claimId is assigned by the harness and must be preserved. "
            "The quantity is base-asset quantity. A LIMIT claim needs a positive price. A MARKET claim must "
            "set price to null. Keep status NEW for an unfilled limit proposal.\n\n"
            f"MANDATE_JSON={json.dumps(mandate, ensure_ascii=True)}\n"
            f"CLAIM_ID={claim_id}\n"
            f"LIVE_CONTEXT_JSON={json.dumps(context.to_mapping(), sort_keys=True)}\n\n"
            "Required JSON keys: claimId, mandate, symbol, side, orderType, quantity, price, status, reason. "
            "No additional keys. Keep reason between 1 and 1000 characters."
        )

    @staticmethod
    def _retry_prompt(mandate: str, claim_id: str, context: MarketContext) -> str:
        return (
            "Your previous response failed strict validation. Return only one valid JSON object. "
            "Do not use markdown, comments, code fences, unknown keys, or tool calls. "
            f"MANDATE_JSON={json.dumps(mandate, ensure_ascii=True)}\n"
            f"CLAIM_ID={claim_id}\n"
            f"LIVE_CONTEXT_JSON={json.dumps(context.to_mapping(), sort_keys=True)}\n"
            "Required keys: claimId, mandate, symbol, side, orderType, quantity, price, status, reason."
        )

    @staticmethod
    def _parse_claim(response: str, claim_id: str, mandate: str, symbol: str) -> Claim:
        payload = json.loads(response)
        claim = Claim.from_mapping(payload)
        if claim.claim_id != claim_id:
            raise AgentOutputError("LLM changed the harness-assigned claim ID")
        if claim.mandate != mandate or claim.symbol != symbol:
            raise AgentOutputError("LLM changed the harness-bound mandate or symbol")
        return claim
