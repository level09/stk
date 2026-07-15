"""Best-effort cost and provider usage tracking for one Qarina run."""

from __future__ import annotations

import os
import threading
from typing import Any

import httpx

_pricing_cache: dict[str, dict[str, float]] | None = None
_pricing_lock = threading.Lock()


def _openrouter_pricing() -> dict[str, dict[str, float]]:
    global _pricing_cache
    if _pricing_cache is not None:
        return _pricing_cache
    with _pricing_lock:
        if _pricing_cache is not None:
            return _pricing_cache
        try:
            response = httpx.get(
                "https://openrouter.ai/api/v1/models", timeout=5.0
            )
            response.raise_for_status()
            pricing = {}
            for model in response.json().get("data", []):
                rates = model.get("pricing") or {}
                prompt = float(rates.get("prompt", 0)) * 1_000_000
                completion = float(rates.get("completion", 0)) * 1_000_000
                pricing[model["id"]] = {
                    "prompt": prompt,
                    "completion": completion,
                }
            _pricing_cache = pricing
        except Exception:
            _pricing_cache = {}
        return _pricing_cache


def _usage_value(usage: Any, name: str) -> int:
    value = getattr(usage, name, 0) if usage else 0
    return int(value or 0)


class CostLedger:
    """Collect provider usage and calculate a clearly labeled estimate."""

    def __init__(
        self,
        *,
        model_pricing: dict[str, dict[str, float]] | None = None,
        serper_cost_per_query: float | None = None,
    ):
        self._lock = threading.Lock()
        self.model_pricing = model_pricing
        self.serper_cost_per_query = (
            float(
                os.environ.get("SERPER_COST_PER_QUERY", "0")
                if serper_cost_per_query is None
                else serper_cost_per_query
            )
        )
        self.openrouter_calls: list[dict[str, Any]] = []
        self.serper_queries = 0
        self.serper_categories: dict[str, int] = {}

    def record_openrouter(self, response: Any, *, purpose: str) -> None:
        usage = getattr(response, "usage", None)
        model = getattr(response, "model", "") or "unknown"
        prompt_tokens = _usage_value(usage, "prompt_tokens")
        completion_tokens = _usage_value(usage, "completion_tokens")
        rates = (self.model_pricing or {}).get(model)
        if rates is None:
            rates = _openrouter_pricing().get(model)
        estimated_usd = None
        if rates:
            estimated_usd = (
                prompt_tokens * rates["prompt"]
                + completion_tokens * rates["completion"]
            ) / 1_000_000
        with self._lock:
            self.openrouter_calls.append(
                {
                    "purpose": purpose,
                    "model": model,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": _usage_value(usage, "total_tokens")
                    or prompt_tokens + completion_tokens,
                    "estimated_usd": estimated_usd,
                }
            )

    def record_serper(self, category: str) -> None:
        with self._lock:
            self.serper_queries += 1
            self.serper_categories[category] = (
                self.serper_categories.get(category, 0) + 1
            )

    def summary(self) -> dict[str, Any]:
        with self._lock:
            calls = [*self.openrouter_calls]
            serper_queries = self.serper_queries
            categories = dict(self.serper_categories)
        openrouter_costs = [
            call["estimated_usd"]
            for call in calls
            if call["estimated_usd"] is not None
        ]
        openrouter_total = sum(openrouter_costs)
        serper_total = serper_queries * self.serper_cost_per_query
        total = openrouter_total + serper_total
        pricing_complete = len(openrouter_costs) == len(calls) and (
            not serper_queries or self.serper_cost_per_query > 0
        )
        return {
            "currency": "USD",
            "estimated_usd": round(total, 6),
            "pricing_complete": pricing_complete,
            "openrouter": {
                "calls": len(calls),
                "prompt_tokens": sum(c["prompt_tokens"] for c in calls),
                "completion_tokens": sum(c["completion_tokens"] for c in calls),
                "total_tokens": sum(c["total_tokens"] for c in calls),
                "estimated_usd": round(openrouter_total, 6),
            },
            "serper": {
                "queries": serper_queries,
                "categories": categories,
                "cost_per_query_usd": self.serper_cost_per_query,
                "estimated_usd": round(serper_total, 6),
            },
            "openrouter_calls": calls,
        }


def tracked_chat_completion(client, ledger: CostLedger | None, *, purpose: str, **kwargs):
    response = client.chat.completions.create(**kwargs)
    if ledger is not None:
        ledger.record_openrouter(response, purpose=purpose)
    return response
