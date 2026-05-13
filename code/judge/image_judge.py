"""A5 Image-level Visual Quality judge (v0.3 amendment D7.2 / §7.2-7.3).

Primary judge: Claude Sonnet (latest vision-capable) via the `claude -p`
CLI in headless mode. Uses the user's Claude Code session credits so
high-volume image judging stays well below pay-per-call API budget.

Per AMENDMENT_v0.3_ACTION_SPEC.md §7.2:
  - readability ∈ [0, 1]: labels visible, no truncation, no overlap
  - layout      ∈ [0, 1]: alignment, balance, spacing
  - overall     ∈ [0, 1]: end-user usability given the query intent

The CLI invocation:
  claude -p "<prompt>" --model sonnet --output-format json --add-dir <img-dir>

The wrapper:
  - injects an explicit time-sleep between calls (default 3s) to respect
    rate limits and avoid session-cap throttling
  - retries on transient errors with exponential backoff
  - parses the result JSON, then extracts the inner ```json {...} ``` block
    Sonnet wraps its answer in
  - returns a typed dataclass + raw cost/usage for telemetry
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


PROMPT_TEMPLATE = """\
You are an A5 visual-quality judge for document-grounded visualizations.

The rendered visualization is the PNG image at: {image_path}

Read that image, then score it on three dimensions on a 0/0.5/1 ordinal scale
(0=poor, 0.5=acceptable, 1=excellent). Use values from {{0, 0.5, 1}} only.

Context for assessment:
  - User query (what the visualization should answer):
    "{query}"
  - Declared visualization type: {viz_type}
  - Query type: {query_type}

Scoring dimensions:
  1. readability — labels visible, no truncation, no overlap, legend
     clear (if present), axes readable. A label that overlaps or is
     clipped → 0. Fully readable → 1.
  2. layout — alignment, balance, spacing, no crowded clusters in one
     corner, sensible margins. Cramped/skewed → 0. Well-composed → 1.
  3. overall — end-user usability given the query intent. Does this
     visualization actually answer the question? Aesthetic appeal is
     secondary to functional clarity.

Return ONLY one JSON object with exactly these four keys:
  {{"readability": <0|0.5|1>,
    "layout":      <0|0.5|1>,
    "overall":     <0|0.5|1>,
    "justification": "<one short sentence, ≤30 words>"}}

No prose outside the JSON. No markdown fences.
"""


@dataclass
class ImageJudgeResult:
    """Outcome of a single image-judge call."""
    readability: Optional[float] = None
    layout: Optional[float] = None
    overall: Optional[float] = None
    justification: str = ""
    raw_result: str = ""
    cost_usd: float = 0.0
    duration_ms: int = 0
    success: bool = False
    error: str = ""
    attempts: int = 0


def _resolve_claude() -> str:
    found = shutil.which("claude")
    if found:
        return found
    home_local = Path.home() / ".local" / "bin" / "claude"
    if home_local.is_file():
        return str(home_local)
    raise RuntimeError("`claude` CLI not found on PATH or ~/.local/bin")


_FENCED_JSON_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_INLINE_JSON_RE = re.compile(r"\{[^{}]*\"readability\"[^{}]*\}", re.DOTALL)


def _parse_result_block(result_text: str) -> Optional[Dict[str, Any]]:
    """Pull the inner {readability, layout, overall, justification} JSON
    out of Sonnet's typically-fenced answer."""
    if not result_text:
        return None
    # Strategy 1: fenced ```json {...} ```
    m = _FENCED_JSON_RE.search(result_text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # Strategy 2: bare JSON object containing "readability"
    m = _INLINE_JSON_RE.search(result_text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    # Strategy 3: whole-text JSON
    try:
        return json.loads(result_text.strip())
    except json.JSONDecodeError:
        return None


def _coerce_score(v: Any) -> Optional[float]:
    if isinstance(v, (int, float)):
        f = float(v)
        if f in (0.0, 0.5, 1.0):
            return f
        # Snap to nearest allowed value
        if f <= 0.25:
            return 0.0
        if f <= 0.75:
            return 0.5
        return 1.0
    return None


def judge_image(
    image_path: str | Path,
    record: Dict[str, Any],
    *,
    model: str = "sonnet",
    sleep_seconds: float = 3.0,
    max_retries: int = 3,
    add_dir: Optional[str] = None,
    timeout_seconds: int = 90,
) -> ImageJudgeResult:
    """Judge a single rendered image. Returns an ImageJudgeResult.

    `sleep_seconds` is enforced AFTER each successful call (the caller is
    responsible for the rhythm); 3s default is conservative for keeping
    `claude -p` session credits stable across a 100-record sub-sample.
    """
    image_path = str(Path(image_path).resolve())
    if not Path(image_path).exists():
        return ImageJudgeResult(error=f"image not found: {image_path}")

    add_dir = add_dir or str(Path(image_path).parent)

    prompt = PROMPT_TEMPLATE.format(
        image_path=image_path,
        query=(record.get("query") or "")[:500],
        viz_type=record.get("viz_type", ""),
        query_type=record.get("query_type", ""),
    )

    try:
        claude_bin = _resolve_claude()
    except RuntimeError as e:
        return ImageJudgeResult(error=str(e))

    cmd = [
        claude_bin, "-p", prompt,
        "--model", model,
        "--output-format", "json",
        "--add-dir", add_dir,
    ]

    backoff = 4.0
    last_err = ""
    raw = ""
    cost = 0.0
    dur = 0
    for attempt in range(1, max_retries + 1):
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout_seconds,
            )
            if proc.returncode != 0:
                last_err = (proc.stderr or proc.stdout or "").strip()[:300]
                time.sleep(backoff)
                backoff = min(backoff * 2.0, 30.0)
                continue
            try:
                data = json.loads(proc.stdout)
            except json.JSONDecodeError as e:
                last_err = f"CLI stdout not JSON: {e}; head={proc.stdout[:200]!r}"
                time.sleep(backoff)
                backoff = min(backoff * 2.0, 30.0)
                continue
            if data.get("is_error"):
                last_err = data.get("result", "")[:300]
                # Honor any rate limit framing
                if "rate" in last_err.lower() or "limit" in last_err.lower():
                    time.sleep(max(backoff, 10.0))
                    backoff = min(backoff * 2.0, 60.0)
                continue
            raw = data.get("result", "")
            cost = float(data.get("total_cost_usd", 0) or 0)
            dur = int(data.get("duration_ms", 0) or 0)

            parsed = _parse_result_block(raw)
            if not parsed:
                last_err = f"failed to extract JSON from result: head={raw[:200]!r}"
                time.sleep(backoff)
                backoff = min(backoff * 2.0, 30.0)
                continue

            res = ImageJudgeResult(
                readability=_coerce_score(parsed.get("readability")),
                layout=_coerce_score(parsed.get("layout")),
                overall=_coerce_score(parsed.get("overall")),
                justification=str(parsed.get("justification", "")).strip(),
                raw_result=raw,
                cost_usd=cost,
                duration_ms=dur,
                success=True,
                attempts=attempt,
            )
            # Validate all three scores parsed
            if any(s is None for s in (res.readability, res.layout, res.overall)):
                res.success = False
                res.error = (
                    f"one or more axis scores missing/invalid in JSON: {parsed}"
                )
            # Throttle after a successful call
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)
            return res
        except subprocess.TimeoutExpired:
            last_err = f"CLI timeout after {timeout_seconds}s"
            time.sleep(backoff)
            backoff = min(backoff * 2.0, 60.0)
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            time.sleep(backoff)
            backoff = min(backoff * 2.0, 60.0)

    return ImageJudgeResult(
        raw_result=raw,
        cost_usd=cost,
        duration_ms=dur,
        success=False,
        error=last_err,
        attempts=max_retries,
    )


def judge_image_batch(
    records: List[Dict[str, Any]],
    images_dir: str | Path,
    *,
    model: str = "sonnet",
    sleep_seconds: float = 3.0,
    add_dir: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Batch image judging; same convention as compute_clipscore_batch.

    Returns a list of dicts: {query_id, strategy, image_path, judge:
    {readability, layout, overall, justification}, cost_usd, ...}.
    """
    images_dir = Path(images_dir)
    out: List[Dict[str, Any]] = []
    for r in records:
        qid = r.get("query_id", "unknown")
        strat = r.get("strategy", "unknown")
        path = images_dir / strat / f"{qid}.png"
        if not path.exists():
            out.append({
                "query_id": qid, "strategy": strat,
                "image_path": str(path), "success": False,
                "error": "image missing",
            })
            continue
        res = judge_image(
            path, r,
            model=model, sleep_seconds=sleep_seconds, add_dir=add_dir,
        )
        out.append({
            "query_id": qid,
            "strategy": strat,
            "image_path": str(path),
            "readability": res.readability,
            "layout": res.layout,
            "overall": res.overall,
            "justification": res.justification,
            "cost_usd": res.cost_usd,
            "duration_ms": res.duration_ms,
            "attempts": res.attempts,
            "success": res.success,
            "error": res.error,
        })
    return out
