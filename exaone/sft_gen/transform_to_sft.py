"""Convert 3k batch_*.jsonl + run trace dirs → guide-spec SFT train.jsonl.

Reads:
  - input dir of batch_*.jsonl rows (the multi-host gathered SFT batch outputs)
  - traces dir of per-run subdirs containing raw_run_result.json +
    auxiliary_*.json (this host's slice; others stay unmatched and rely on
    prompt/tool reconstruction)

Outputs one JSONL line per:
  - main rollout record (per guide §0)
  - one aux record per web_extract LLM call (per guide §A.2)
  - one aux record per ReadFullDocument call, reconstructed retroactively
    from the docai parsing JSON + tool_call goal + tool_result text
    (matches `auxiliary_rd_extract_N.json` content the runtime hook now
    writes, but reconstructed for pre-hook 3k v2 data)

Loss masking computed per guide §1 (single + multi-turn rules).

CLI:
    python -m exaone.sft_gen.transform_to_sft \\
        --input data/sft_3k_v2 \\
        --traces logs/exaone_traces \\
        --output train_data/SFT/docqa_hermes/260527/train.jsonl
"""

from __future__ import annotations

import glob
import json
import logging
import os
import re
import sys
from collections import Counter
from datetime import datetime, date
from pathlib import Path
from typing import Any, Iterable, Optional

import fire

from exaone.docqa_tools._extractor_prompts import EXTRACTOR_DOC_PROMPT
from exaone.sft_gen.shim.pdf_index import _build_index as _build_pdf_index

logger = logging.getLogger(__name__)


_RFD_CONTENT_CAP = 50_000   # mirrors handle_read_full_document.py _CONTENT_CHAR_CAP


# ─── prompt-block assembly (matches compose_system_prompt order) ────────────

def _assemble_system_from_blocks(blocks: dict[str, str]) -> str:
    """Join blocks in the canonical order (matches compose_system_prompt)."""
    parts: list[str] = []
    for key in ("identity", "tool_list", "style", "custom", "memory"):
        v = (blocks.get(key) or "").strip()
        if v:
            parts.append(v)
    return "\n\n".join(parts)


def _reconstruct_blocks(qa_mode: str) -> dict[str, str]:
    """For batch rows without a matching raw trace, rebuild from disk prompts."""
    from exaone.system_prompt import compose_wire_strict
    from exaone.qa_modes import resolve_qa_mode
    cfg = resolve_qa_mode(qa_mode)
    _, _, blocks = compose_wire_strict(
        identity_name=cfg.identity_name,
        style_name=cfg.style_name,
        tool_ids=[],   # tool_list block populated by ExaoneAgent at runtime;
                       # for retro we accept an empty tool_list rather than
                       # invent one, since the actual run may have had a
                       # different subset.
    )
    return blocks


# ─── messages → conversations conversion ────────────────────────────────────

def _convert_msg(msg: dict[str, Any]) -> dict[str, Any]:
    """Pass through OpenAI msg, normalizing the assistant tool_calls shape."""
    role = msg.get("role")
    out: dict[str, Any] = {"role": role}
    content = msg.get("content")
    if isinstance(content, list):
        # multimodal blocks — collapse to text-only for SFT
        text_parts = [p.get("text", "") for p in content if isinstance(p, dict)]
        content = "\n".join(p for p in text_parts if p)
    out["content"] = content or ""
    if role == "assistant":
        reasoning = msg.get("reasoning_content") or msg.get("reasoning") or ""
        out["reasoning_content"] = reasoning
        tool_calls = msg.get("tool_calls") or []
        if tool_calls:
            out["tool_calls"] = []
            for tc in tool_calls:
                fn = tc.get("function") or {}
                args = fn.get("arguments")
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {}
                out["tool_calls"].append({
                    "id": tc.get("id"),
                    "type": tc.get("type", "function"),
                    "function": {"name": fn.get("name"), "arguments": args},
                })
    elif role == "tool":
        out["tool_call_id"] = msg.get("tool_call_id") or ""
        out["name"] = msg.get("name") or ""
    return out


def _build_conversations(
    *, raw_messages: list[dict[str, Any]] | None,
    sharegpt_conversations: list[dict[str, Any]] | None,
    system_content: str,
) -> list[dict[str, Any]]:
    """Build guide-spec conversations list.

    Drops upstream's `_empty_recovery_synthetic` turns so the training
    trajectory looks like a clean run. The agent's internal protocol
    nudge (synthetic ass "(empty)" + synthetic user retry prompt) is
    a wire-format trick to keep the API happy — it carries no signal we
    want the SFT model to learn, and it falsely promotes a single-turn
    trace into a multi-turn one (which then mis-classifies the original
    pre-recovery rollout as `history`).
    """
    out: list[dict[str, Any]] = [{"role": "system", "content": system_content}]

    if raw_messages:
        # OpenAI format messages — skip any existing system turn AND any
        # synthetic recovery turn (both ass "(empty)" and user retry prompt
        # are flagged `_empty_recovery_synthetic: True` by run_agent.py).
        for m in raw_messages:
            if m.get("role") == "system":
                continue
            if m.get("_empty_recovery_synthetic"):
                continue
            out.append(_convert_msg(m))
        return out

    if sharegpt_conversations:
        # ShareGPT format ({from, value}) — convert and skip the hardcoded system.
        for c in sharegpt_conversations:
            f = c.get("from")
            v = c.get("value") or ""
            if f == "system":
                continue
            if f in ("human", "user"):
                out.append({"role": "user", "content": v})
            elif f in ("gpt", "assistant"):
                # ShareGPT may embed <think>...</think> and <tool_call>...
                # Extract them back to OpenAI-shape best-effort.
                out.append(_parse_sharegpt_assistant(v))
            elif f in ("tool", "function"):
                out.append(_parse_sharegpt_tool(v))
    return out


def _parse_sharegpt_assistant(value: str) -> dict[str, Any]:
    """Best-effort revert from ShareGPT-flattened assistant turn to dict."""
    out: dict[str, Any] = {"role": "assistant"}
    reasoning = ""
    m = re.search(r"<think>\s*(.*?)\s*</think>", value, re.DOTALL)
    if m:
        reasoning = m.group(1)
        value = value.replace(m.group(0), "", 1)
    out["reasoning_content"] = reasoning

    tool_calls = []
    for tc_match in re.finditer(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", value, re.DOTALL):
        try:
            parsed = json.loads(tc_match.group(1).replace("'", '"'))
            tool_calls.append({
                "type": "function",
                "function": {"name": parsed.get("name", ""),
                             "arguments": parsed.get("arguments", {})},
            })
        except Exception:
            continue
    if tool_calls:
        out["tool_calls"] = tool_calls
        # strip from content
        value = re.sub(r"<tool_call>\s*\{.*?\}\s*</tool_call>\s*", "", value, flags=re.DOTALL)
    out["content"] = value.strip()
    return out


def _parse_sharegpt_tool(value: str) -> dict[str, Any]:
    """Revert <tool_response>{...}</tool_response> to tool dict."""
    m = re.match(r"\s*<tool_response>\s*(\{.*\})\s*</tool_response>\s*", value, re.DOTALL)
    if m:
        try:
            payload = json.loads(m.group(1))
            return {
                "role": "tool",
                "tool_call_id": payload.get("tool_call_id") or "",
                "name": payload.get("name") or "",
                "content": json.dumps(payload.get("content"), ensure_ascii=False)
                           if not isinstance(payload.get("content"), str)
                           else payload.get("content"),
            }
        except Exception:
            pass
    return {"role": "tool", "tool_call_id": "", "name": "", "content": value}


# ─── loss masking (guide §1) ────────────────────────────────────────────────

def _apply_loss_masking(convs: list[dict[str, Any]]) -> None:
    """Apply guide §1 loss_masking.

    Single-turn (1 user): every ass turn after that user is rollout
    (loss_masking=False). reasoning_content is preserved on every ass
    turn (guide §2 stripping rule only applies to multi-turn history).

    Multi-turn (2+ users): ass turns before the last user are history
    (loss=True + reasoning stripped per §2). Ass turns after the last
    user are rollout (loss=False, reasoning kept).
    """
    user_indices = [i for i, c in enumerate(convs) if c.get("role") == "user"]
    n_users = len(user_indices)
    last_user_idx = user_indices[-1] if user_indices else -1
    is_multi_turn = n_users >= 2

    for i, c in enumerate(convs):
        role = c.get("role")
        if role != "assistant":
            c["loss_masking"] = True
            continue
        if is_multi_turn and i < last_user_idx:
            # history assistant — strip reasoning per §2
            c["loss_masking"] = True
            c["reasoning_content"] = ""
        else:
            # single-turn (n_users <= 1) OR rollout in multi-turn
            c["loss_masking"] = False


# ─── validation (basic — see guide §3,4,6) ──────────────────────────────────

_CITATION_RE = re.compile(r"\[([A-Za-z0-9_]{3,}\.\d+)\]")
_CODE_BLOCK_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")


def _mask_code(text: str) -> str:
    text = _CODE_BLOCK_RE.sub("", text)
    text = _INLINE_CODE_RE.sub("", text)
    return text


def _validate_record(rec: dict[str, Any]) -> str | None:
    """Return None when valid, else a short reason for the drop."""
    convs = rec.get("conversations") or []
    if not convs:
        return "empty_conversations"

    # §6.1 — system at index 0
    if convs[0].get("role") != "system":
        return "missing_system_turn"

    # §6.2 — last turn = assistant with non-empty content + no tool_calls
    last = convs[-1]
    if last.get("role") != "assistant":
        return "last_not_assistant"
    if last.get("tool_calls"):
        return "last_has_tool_calls"
    if not (last.get("content") or "").strip():
        return "last_empty_content"

    # §3.4 — tcid uniqueness
    seen_tcid: set[str] = set()
    for c in convs:
        if c.get("role") == "tool":
            tcid = c.get("tool_call_id") or ""
            if tcid in seen_tcid:
                return "duplicate_tcid"
            seen_tcid.add(tcid)

    # §4.1 — cited_set ⊆ valid_set
    valid_set: set[str] = set()
    for c in convs:
        if c.get("role") == "tool":
            content = c.get("content") or ""
            try:
                envelope = json.loads(content) if isinstance(content, str) else content
            except Exception:
                continue
            if isinstance(envelope, dict):
                results = envelope.get("results") or []
                for r in results:
                    if isinstance(r, dict) and "Index" in r:
                        valid_set.add(str(r["Index"]))

    # cited_set from rollout assistant turns only
    last_user_idx = max(
        (i for i, c in enumerate(convs) if c.get("role") == "user"), default=-1
    )
    cited_set: set[str] = set()
    for i, c in enumerate(convs):
        if c.get("role") != "assistant" or i <= last_user_idx:
            continue
        for field in ("content", "reasoning_content"):
            txt = c.get(field) or ""
            txt = _mask_code(txt)
            for m in _CITATION_RE.findall(txt):
                cited_set.add(m)

    bad = cited_set - valid_set
    if bad:
        return f"citation_hallucination:{len(bad)}"

    return None


# ─── aux instance derivation ────────────────────────────────────────────────

def _convert_aux_conversations(
    raw_convs: list[dict[str, Any]], for_user_loss_true: bool = True,
) -> list[dict[str, Any]]:
    """Apply loss_masking per guide §A.4."""
    out: list[dict[str, Any]] = []
    for c in raw_convs:
        role = c.get("role")
        loss = role != "assistant"
        out.append({
            "role": role,
            "content": c.get("content") or "",
            "loss_masking": loss,
        })
    return out


def _derive_web_extract_aux(
    *, qid: str, run_dir: Path,
) -> Iterable[dict[str, Any]]:
    """One record per auxiliary_web_extract_*.json file."""
    for aux_file in sorted(run_dir.glob("auxiliary_web_extract_*.json")):
        try:
            data = json.load(aux_file.open())
        except Exception:
            continue
        m = re.search(r"auxiliary_web_extract_(\d+)\.json", aux_file.name)
        seq = m.group(1) if m else "1"
        yield {
            "id": f"{qid}_aux_web_extract_{seq}",
            "conversations": _convert_aux_conversations(data.get("conversations") or []),
            "meta": {"kind": "web_extract", **(data.get("meta") or {})},
        }


def _derive_rd_extract_aux_retro(
    *, qid: str, main_convs: list[dict[str, Any]], pdf_index,
) -> Iterable[dict[str, Any]]:
    """Retro-reconstruct RFD aux instances from main trajectory.

    Pre-hook 3k v2 data has no auxiliary_rd_extract_*.json files. Rebuild
    the input prompt (EXTRACTOR_DOC_PROMPT + doc text + goal) from the
    docai parsing JSON and pair with the tool_result text. Output is what
    the runtime hook would have written if it had existed at gen time.
    """
    pair_idx = 0
    for i, c in enumerate(main_convs):
        if c.get("role") != "assistant":
            continue
        for tc in c.get("tool_calls") or []:
            if (tc.get("function") or {}).get("name") != "ReadFullDocument":
                continue
            # find the next tool turn matching this tcid
            tcid = tc.get("id")
            result_msg = next(
                (m for m in main_convs[i + 1:]
                 if m.get("role") == "tool" and m.get("tool_call_id") == tcid),
                None,
            )
            if result_msg is None:
                continue
            try:
                envelope = json.loads(result_msg.get("content") or "{}")
            except Exception:
                continue
            # RFD result envelope shape (after TOOL_RESULT_FORMATS):
            #   {"results": [{Index, text, filename, goal, ...}]}
            # Older shape (no formatter wrap): {text, filename, goal} at top.
            payload: dict = {}
            if isinstance(envelope, dict):
                results = envelope.get("results") or []
                if results and isinstance(results[0], dict):
                    payload = results[0]
                else:
                    payload = envelope
            extracted_text = payload.get("text") or ""
            if not extracted_text:
                continue
            # Skip error rows (no text returned, just an `error` field).
            if payload.get("error"):
                continue
            filename = payload.get("filename") or ""
            goal = payload.get("goal") or ""
            entry = pdf_index.lookup(filename) if filename else None
            if entry is None:
                continue
            joined = _load_doc_full_text(entry.parsed_json_path)
            if not joined:
                continue
            content_capped = joined[:_RFD_CONTENT_CAP]
            user_prompt = EXTRACTOR_DOC_PROMPT.format(
                webpage_content=content_capped, goal=goal,
            )
            pair_idx += 1
            yield {
                "id": f"{qid}_aux_rd_extract_{pair_idx}",
                "conversations": [
                    {"role": "user", "content": user_prompt, "loss_masking": True},
                    {"role": "assistant", "content": extracted_text, "loss_masking": False},
                ],
                "meta": {
                    "kind": "rd_extract", "filename": filename, "goal": goal,
                    "content_char_count": len(content_capped),
                    "content_truncated": len(joined) > _RFD_CONTENT_CAP,
                    "retro": True,
                },
            }


def _load_doc_full_text(parsed_json_path: Path) -> str:
    """Mirror handle_read_full_document.py's join: list_parsed pages with [Page N]."""
    try:
        d = json.load(parsed_json_path.open("rb"))
    except Exception:
        return ""
    outputs = d.get("outputs") or []
    if not outputs:
        return ""
    pages = (outputs[0] or {}).get("list_parsed") or {}
    if not pages:
        return ""
    parts: list[str] = []
    for page_key in sorted(pages.keys(), key=lambda k: int(k) if str(k).isdigit() else 9999):
        chunks = pages.get(page_key) or []
        if isinstance(chunks, list):
            text = "\n\n".join(str(c) for c in chunks)
        else:
            text = str(chunks)
        parts.append(f"[Page {page_key}]\n{text}".rstrip())
    return "\n\n".join(parts)


# ─── raw trace index (user_query → raw_run_result.json path) ───────────────

def _build_raw_index(traces_dir: Path) -> dict[str, Path]:
    """Map exact user_query string → raw_run_result.json path.

    May miss matches when multiple hosts share a user_query — for 3k v2
    each prompt is unique, so this is fine in practice.
    """
    idx: dict[str, Path] = {}
    for p in traces_dir.glob("*/*/raw_run_result.json"):
        try:
            with p.open("rb") as f:
                d = json.load(f)
        except Exception:
            continue
        uq = d.get("user_query") or ""
        if uq and uq not in idx:
            idx[uq] = p
    return idx


# ─── per-batch-row conversion ──────────────────────────────────────────────

def _extract_user_query_from_batch(row: dict[str, Any]) -> str:
    for c in row.get("conversations") or []:
        if c.get("from") in ("human", "user"):
            return c.get("value") or ""
    return ""


def _convert_row(
    *, row: dict[str, Any], raw_path: Optional[Path], pdf_index,
) -> tuple[Optional[dict[str, Any]], list[dict[str, Any]], Optional[str]]:
    """Return (main_record, aux_records, drop_reason_or_None)."""
    raw: Optional[dict[str, Any]] = None
    if raw_path is not None:
        try:
            raw = json.load(raw_path.open("rb"))
        except Exception:
            raw = None

    qid = (raw or {}).get("query_id") or f"batch_{row.get('prompt_index')}"

    qa_mode = ((row.get("metadata") or {}).get("qa_mode")) or "docqa"
    if raw and raw.get("system_blocks"):
        blocks = dict(raw["system_blocks"])
    else:
        try:
            blocks = _reconstruct_blocks(qa_mode)
        except Exception:
            return None, [], "blocks_unavailable"

    tools = (raw or {}).get("tool_schemas") or []
    system_content = _assemble_system_from_blocks(blocks)

    convs = _build_conversations(
        raw_messages=(raw or {}).get("messages"),
        sharegpt_conversations=row.get("conversations"),
        system_content=system_content,
    )
    _apply_loss_masking(convs)

    main_rec = {
        "id": qid,
        "system_blocks": blocks,
        "available_tools": [t.get("function", {}).get("name") for t in tools],
        "tools": tools,
        "conversations": convs,
    }
    drop = _validate_record(main_rec)
    if drop:
        return None, [], drop

    aux: list[dict[str, Any]] = []
    if raw_path is not None:
        run_dir = raw_path.parent
        aux.extend(_derive_web_extract_aux(qid=qid, run_dir=run_dir))
    aux.extend(_derive_rd_extract_aux_retro(
        qid=qid, main_convs=convs, pdf_index=pdf_index,
    ))
    return main_rec, aux, None


# ─── CLI ───────────────────────────────────────────────────────────────────

def main(
    input: str = "data/sft_3k_v3",
    traces: str = "logs/exaone_traces",
    output: str = "train_data/SFT/docqa/trajectory/260527/train.jsonl",
    aux_web_extract: str = "train_data/SFT/docqa/web_extract/260527/train.jsonl",
    aux_rfd: str = "train_data/SFT/docqa/readfulldocument/260527/train.jsonl",
    limit: Optional[int] = None,
):
    """Convert batch outputs + run traces → guide-spec SFT JSONL.

    Splits output into three files: main trajectory, web_extract aux,
    readfulldocument aux. Each aux file is gated by its CLI path — pass
    an empty string to skip that aux stream entirely.
    """
    logging.basicConfig(level=logging.WARNING)

    in_dir = Path(input)
    traces_dir = Path(traces)
    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    aux_we_path = Path(aux_web_extract) if aux_web_extract else None
    aux_rd_path = Path(aux_rfd) if aux_rfd else None
    for p in (aux_we_path, aux_rd_path):
        if p:
            p.parent.mkdir(parents=True, exist_ok=True)

    print(f"[transform_to_sft] building raw_run_result index over {traces_dir} ...")
    raw_index = _build_raw_index(traces_dir)
    print(f"  raw traces indexed: {len(raw_index)}")

    print(f"[transform_to_sft] building docai pdf index ...")
    pdf_index = _build_pdf_index()
    print(f"  docai entries: {len(pdf_index._by_basename)}")

    stats: Counter = Counter()
    batch_files = sorted(in_dir.glob("batch_*.jsonl"))
    print(f"[transform_to_sft] {len(batch_files)} batch files")
    print(f"  main → {out_path}")
    if aux_we_path:
        print(f"  aux web_extract → {aux_we_path}")
    if aux_rd_path:
        print(f"  aux readfulldocument → {aux_rd_path}")

    aux_we_fh = aux_we_path.open("w", encoding="utf-8") if aux_we_path else None
    aux_rd_fh = aux_rd_path.open("w", encoding="utf-8") if aux_rd_path else None
    try:
        with out_path.open("w", encoding="utf-8") as out:
            for bf in batch_files:
                for line in bf.open("r", encoding="utf-8"):
                    if not line.strip():
                        continue
                    stats["in"] += 1
                    try:
                        row = json.loads(line)
                    except Exception:
                        stats["drop:json"] += 1
                        continue

                    uq = _extract_user_query_from_batch(row)
                    raw_path = raw_index.get(uq)
                    if raw_path is None:
                        stats["raw_missing"] += 1

                    main_rec, aux_recs, drop = _convert_row(
                        row=row, raw_path=raw_path, pdf_index=pdf_index,
                    )
                    if main_rec is None:
                        stats[f"drop:{drop}"] += 1
                        continue

                    out.write(json.dumps(main_rec, ensure_ascii=False) + "\n")
                    stats["main_written"] += 1
                    for ar in aux_recs:
                        kind = ar["meta"].get("kind", "?")
                        line_out = json.dumps(ar, ensure_ascii=False) + "\n"
                        if kind == "web_extract" and aux_we_fh:
                            aux_we_fh.write(line_out)
                            stats["aux:web_extract"] += 1
                        elif kind == "rd_extract" and aux_rd_fh:
                            aux_rd_fh.write(line_out)
                            stats["aux:rd_extract"] += 1
                        else:
                            stats[f"aux:{kind}:unrouted"] += 1

                    if limit is not None and stats["main_written"] >= limit:
                        break
                if limit is not None and stats["main_written"] >= limit:
                    break
    finally:
        if aux_we_fh:
            aux_we_fh.close()
        if aux_rd_fh:
            aux_rd_fh.close()

    print(f"\n[transform_to_sft] DONE")
    for k in sorted(stats):
        print(f"  {k}: {stats[k]}")


if __name__ == "__main__":
    fire.Fire(main)
