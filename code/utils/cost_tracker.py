"""Lightweight token + $ tracker.

Week 0 runs entirely on on-premise Qwen3.6-27B (cost = 0). This module exists
to:
  - count tokens per call (in/out) so we can verify the prototype stays within
    sensible compute bounds before we ever touch closed APIs;
  - enforce the PAPER_MASTER_SPEC §17.x stop-loss when closed-API calls are
    eventually wired in (Week N+).

Usage:
    tracker = CostTracker()
    tracker.add(provider="vllm-qwen36", model="Qwen3.6-27B",
                tokens_in=1234, tokens_out=567, cost_usd=0.0)
    print(tracker.summary())
"""
from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from time import time
from typing import Any, Dict, List, Optional


@dataclass
class CallRecord:
    timestamp: float
    provider: str
    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    tag: str = ""           # free-form, e.g. "S1" / "S4-step3" / "judge-gen"


@dataclass
class StopLoss:
    max_total_usd: float = 200.0   # Week 0 PAPER_MASTER_SPEC stop-loss
    max_total_tokens: Optional[int] = None


class CostTracker:
    def __init__(self, stop_loss: Optional[StopLoss] = None):
        self._lock = threading.Lock()
        self._records: List[CallRecord] = []
        self._stop_loss = stop_loss or StopLoss()
        self._tripped = False

    def add(
        self,
        *,
        provider: str,
        model: str,
        tokens_in: int = 0,
        tokens_out: int = 0,
        cost_usd: float = 0.0,
        tag: str = "",
    ) -> CallRecord:
        rec = CallRecord(
            timestamp=time(),
            provider=provider,
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd,
            tag=tag,
        )
        with self._lock:
            self._records.append(rec)
            self._check_stop_loss()
        return rec

    @property
    def stop_loss_tripped(self) -> bool:
        return self._tripped

    def _check_stop_loss(self) -> None:
        total = sum(r.cost_usd for r in self._records)
        if total >= self._stop_loss.max_total_usd:
            self._tripped = True
        if self._stop_loss.max_total_tokens is not None:
            tot_tok = sum(r.tokens_in + r.tokens_out for r in self._records)
            if tot_tok >= self._stop_loss.max_total_tokens:
                self._tripped = True

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            tot_in = sum(r.tokens_in for r in self._records)
            tot_out = sum(r.tokens_out for r in self._records)
            tot_cost = sum(r.cost_usd for r in self._records)
            by_tag: Dict[str, Dict[str, Any]] = {}
            for r in self._records:
                d = by_tag.setdefault(
                    r.tag or "_untagged",
                    {"calls": 0, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0},
                )
                d["calls"] += 1
                d["tokens_in"] += r.tokens_in
                d["tokens_out"] += r.tokens_out
                d["cost_usd"] += r.cost_usd
            return {
                "calls": len(self._records),
                "tokens_in": tot_in,
                "tokens_out": tot_out,
                "tokens_total": tot_in + tot_out,
                "cost_usd": round(tot_cost, 4),
                "stop_loss_tripped": self._tripped,
                "by_tag": by_tag,
            }

    def dump_jsonl(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for r in self._records:
                f.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")
