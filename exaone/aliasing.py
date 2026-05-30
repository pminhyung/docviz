"""Short, run-scoped tool_call_id aliasing for citation-friendly trajectories."""

from __future__ import annotations

import random
import string

_TCID_ALPHA = string.ascii_lowercase
_TCID_DIGIT = string.digits


class RandomShortAliaser:
    """Map provider tool_call_id → ``[a-z]{3}[0-9]{3}`` alias (idempotent per run)."""

    def __init__(self, *, rng: random.Random | None = None) -> None:
        self._rng = rng or random.Random()
        self._used: set[str] = set()
        self._provider_to_alias: dict[str, str] = {}

    def alias(self, *, provider_id: str, tool_name: str) -> str:
        existing = self._provider_to_alias.get(provider_id)
        if existing is not None:
            return existing
        new = self._draw_unique()
        self._used.add(new)
        self._provider_to_alias[provider_id] = new
        return new

    def reset(self) -> None:
        self._used.clear()
        self._provider_to_alias.clear()

    def _draw_unique(self) -> str:
        for _ in range(1000):
            candidate = "".join(self._rng.choices(_TCID_ALPHA, k=3)) + "".join(
                self._rng.choices(_TCID_DIGIT, k=3)
            )
            if candidate not in self._used:
                return candidate
        raise RuntimeError("could not generate a unique tool_call_id alias after 1000 tries")
