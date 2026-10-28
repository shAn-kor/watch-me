"""Price table and integer cost math (04 section 9.1, UT-AI-08).

All money is integer micro-dollars. Prices are read as `Decimal` and converted
to integers once, so no float touches a cost. Rounding is half up. The cached
input discount is ignored (conservative).
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

_MILLION = 1_000_000


def _micros(usd: Any) -> int:
    """USD (str, int, float or Decimal) to integer micro-dollars."""
    return int((Decimal(str(usd)) * _MILLION).to_integral_value())


class PriceTable:
    def __init__(self, prices: dict[str, dict[str, dict[str, int]]]):
        # provider -> model -> {"in": micros per 1M tokens, "out": ..., "audio_hour": ...}
        self._prices = prices

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> PriceTable:
        table: dict[str, dict[str, dict[str, int]]] = {}
        for provider, models in raw.items():
            if provider.startswith("_") or not isinstance(models, dict):
                continue
            table[provider] = {
                model: {
                    key: _micros(entry[name])
                    for key, name in (
                        ("in", "input_per_million_usd"),
                        ("out", "output_per_million_usd"),
                        ("audio_hour", "audio_per_hour_usd"),
                    )
                    if name in entry
                }
                for model, entry in models.items()
            }
        return cls(table)

    @classmethod
    def from_file(cls, path: str | Path) -> PriceTable:
        with open(path, encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh, parse_float=Decimal))

    def _entry(self, provider: str, model: str) -> dict[str, int]:
        models = self._prices.get(provider)
        if models is None:
            return {}  # unknown provider (mock, local): free
        return models.get(model) or models.get("*") or {}

    def usd_micros(
        self,
        provider: str,
        model: str,
        tokens_in: int = 0,
        tokens_out: int = 0,
        audio_ms: int = 0,
    ) -> int:
        p = self._entry(provider, model)
        total = 0
        if tokens_in or tokens_out:
            total += (
                tokens_in * p.get("in", 0)
                + tokens_out * p.get("out", 0)
                + _MILLION // 2
            ) // _MILLION
        if audio_ms:
            # per hour -> per millisecond, rounded half up once: 0.18 USD/h = 50 micros/s
            total += (audio_ms * p.get("audio_hour", 0) + 1_800_000) // 3_600_000
        return total
