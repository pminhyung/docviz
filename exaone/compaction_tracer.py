"""
exaone/compaction_tracer.py — Compaction triplet logging for ExaoneAgent.

Writes three files per compaction event into the run's trace directory:
  {idx:02d}_step1-{N}_pre_compaction.json        — messages before compress()
  {idx:02d}_step1-{N}_compaction_round_trip.json  — summarizer output text
  {idx:02d}_step1-{N}_post_compaction.json        — messages after compress()

If _handle_max_iterations() fires, the last post_compaction file is renamed
to add a _force_finish suffix.
"""

import json
import logging
from contextvars import ContextVar
from pathlib import Path
from threading import Lock

logger = logging.getLogger(__name__)

_CURRENT_RUN_DIR: ContextVar[Path | None] = ContextVar("exaone_current_run_dir", default=None)
_AUX_COMPACTION_SEQ: ContextVar[int] = ContextVar("exaone_aux_compaction_seq", default=0)
_AUX_SEQ_LOCK = Lock()
_AUX_SEQ_BY_RUN: dict[str, int] = {}


def bind_run_dir(run_dir: Path):
    """Bind the current Exaone run directory for tool-level trace writers."""
    tok_dir = _CURRENT_RUN_DIR.set(run_dir)
    tok_seq = _AUX_COMPACTION_SEQ.set(0)
    with _AUX_SEQ_LOCK:
        _AUX_SEQ_BY_RUN[str(run_dir)] = 0
    return tok_dir, tok_seq


def unbind_run_dir(tok_dir, tok_seq) -> None:
    """Reset run-dir contextvars after a conversation run ends."""
    run_dir = _CURRENT_RUN_DIR.get()
    if run_dir is not None:
        with _AUX_SEQ_LOCK:
            _AUX_SEQ_BY_RUN.pop(str(run_dir), None)
    _CURRENT_RUN_DIR.reset(tok_dir)
    _AUX_COMPACTION_SEQ.reset(tok_seq)


def write_auxiliary_compaction_triplet(
    *,
    source: str,
    subject: str,
    raw_text: str,
    compacted_text: str,
    model: str | None = None,
) -> None:
    """Write pre/round-trip/post files for auxiliary compaction-like steps."""
    run_dir = _CURRENT_RUN_DIR.get()
    if run_dir is None:
        return

    # ``ContextVar`` state is copied per asyncio task, so a task-local counter
    # collides under ``asyncio.gather``. Use a run-shared counter instead.
    run_key = str(run_dir)
    with _AUX_SEQ_LOCK:
        seq = _AUX_SEQ_BY_RUN.get(run_key, 0) + 1
        _AUX_SEQ_BY_RUN[run_key] = seq
    _AUX_COMPACTION_SEQ.set(seq)
    prefix = f"{seq:02d}_step_aux-{source}"

    meta = {
        "source": source,
        "subject": subject,
        "model": model,
    }
    try:
        _write(
            run_dir / f"{prefix}_pre_compaction.json",
            {
                "meta": meta,
                "messages": [{"role": "tool", "name": source, "content": raw_text}],
            },
        )
        _write(
            run_dir / f"{prefix}_compaction_round_trip.json",
            {"meta": meta, "summary": compacted_text},
        )
        _write(
            run_dir / f"{prefix}_post_compaction.json",
            {
                "meta": meta,
                "messages": [{"role": "tool", "name": source, "content": compacted_text}],
            },
        )
    except Exception:
        logger.exception("ExaoneAgent: failed to write auxiliary compaction triplet")


def write_compaction_triplet(
    *,
    run_dir: Path,
    idx: int,
    step_n: int,
    pre_messages: list,
    summary_text: str,
    post_messages: list,
) -> None:
    prefix = f"{idx:02d}_step1-{step_n}"
    try:
        _write(run_dir / f"{prefix}_pre_compaction.json", {"messages": pre_messages})
        _write(run_dir / f"{prefix}_compaction_round_trip.json", {"summary": summary_text})
        _write(run_dir / f"{prefix}_post_compaction.json", {"messages": post_messages})
        logger.debug("compaction triplet written: %s/%s_*", run_dir, prefix)
    except Exception:
        logger.exception("ExaoneAgent: failed to write compaction triplet")


def rename_last_post_compaction_force_finish(run_dir: Path, compaction_count: int) -> None:
    """Rename the last post_compaction file to add _force_finish suffix."""
    for f in sorted(run_dir.glob(f"{compaction_count:02d}_*_post_compaction.json")):
        target = f.with_name(f.stem + "_force_finish.json")
        try:
            f.rename(target)
            logger.debug("renamed %s → %s", f.name, target.name)
        except Exception:
            logger.exception("ExaoneAgent: failed to rename post_compaction file")
        break


def _write(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, default=str, indent=2), encoding="utf-8")
