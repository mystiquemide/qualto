"""Harness-mediated, bounded LLM claim generation."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Protocol

from ..engine.claim import Claim, ClaimValidationError, mint_claim_id


class AgentContextError(RuntimeError):
    """Live context could not be read before the model was called."""


class AgentOutputError(RuntimeError):
    """The model did not produce a valid claim after bounded retries."""


class LLMProviderError(RuntimeError):
    """The configured LLM provider failed without exposing provider details."""


class ContextGateway(Protocol):
    def execute(self, tool_name: str, arguments: Mapping[str, Any] | None = None) -> Any:
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
        timeout_seconds: float = 90.0,
    ) -> None:
        self.binary = binary or os.getenv("QUALTO_HERMES_BIN", "hermes")
        self.timeout_seconds = timeout_seconds

    def complete(self, prompt: str) -> str:
        command = [
            self.binary,
            "--toolsets",
            "",
            "--oneshot",
            prompt,
        ]
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                env=os.environ.copy(),
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
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        self.gateway = gateway
        self.llm = llm or HermesLLM()
        self.quote_asset = quote_asset
        self.max_retries = max_retries

    def generate_claim(self, mandate: str, *, symbol: str = "BNBUSDT") -> Claim:
        if not isinstance(mandate, str) or not 1 <= len(mandate.strip()) <= 500:
            raise ValueError("mandate must contain 1 to 500 characters")
        if not isinstance(symbol, str) or not symbol.isalnum() or symbol.upper() != symbol:
            raise ValueError("symbol must be uppercase alphanumeric text")
        context = self._read_context(symbol)
        claim_id = mint_claim_id()
        prompt = self._prompt(mandate, claim_id, context)
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self.llm.complete(prompt)
                return self._parse_claim(response, claim_id, mandate, symbol)
            except (json.JSONDecodeError, ClaimValidationError, AgentOutputError) as exc:
                last_error = exc
                if attempt < self.max_retries:
                    prompt = self._retry_prompt(mandate, claim_id, context)
                elif isinstance(exc, AgentOutputError):
                    raise
            except LLMProviderError:
                raise
        raise AgentOutputError("LLM output was invalid after bounded retries") from last_error

    def _read_context(self, symbol: str) -> MarketContext:
        try:
            price_payload = self.gateway.execute("spot.tickerPrice", {"symbol": symbol})
            account_payload = self.gateway.execute(
                "spot.getAccount", {"omitZeroBalances": True}
            )
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
        try:
            payload = json.loads(response)
        except json.JSONDecodeError:
            raise
        claim = Claim.from_mapping(payload)
        if claim.claim_id != claim_id:
            raise AgentOutputError("LLM changed the harness-assigned claim ID")
        if claim.mandate != mandate or claim.symbol != symbol:
            raise AgentOutputError("LLM changed the harness-bound mandate or symbol")
        return claim
