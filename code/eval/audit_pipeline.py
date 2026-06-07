"""Trust audit for the v0.4.1 pilot eval pipeline (read-only).

Quantifies where the measurement chain leaks BEFORE any metric is trusted:
  1. qid match rate      run trajectory ↔ gold (via runner dataset prompt match)
  2. gold↔intent consistency  each intent's artifact_type_hint has its gold table/graph
  3. sidecar coverage    B6 emitted artifacts resolve to a sidecar dsl_code
  4. gold internal validity   table cells well-formed; graph edges-by-type

No metric scoring here — only "can we even measure this record" accounting.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

_TOOL_CALL_RE = re.compile(r"<tool_call>\s*(\{[\s\S]*?\})\s*</tool_call>")
_ROLE = {"human": "user", "gpt": "assistant", "system": "system", "tool": "tool"}


def _load_jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def _msgs(r: dict) -> list[dict]:
    out = []
    for m in r.get("conversations", []):
        if "from" in m:
            out.append({"role": _ROLE.get(m["from"], m["from"]), "content": m.get("value", "")})
        else:
            out.append(m)
    return out


def _norm_prompt(s: str) -> str:
    if "[Attached documents]" in s:
        parts = s.split("\n\n", 1)
        s = parts[1] if len(parts) > 1 else s
    s = s.strip()
    return s[-220:] if len(s) > 220 else s


def _qid_match(records: list[dict], dataset: list[dict]) -> tuple[int, int]:
    text_to_qid = {_norm_prompt(row.get("prompt", "")): row.get("qid") for row in dataset}
    matched = 0
    for r in records:
        first_user = next((str(m.get("content", "")) for m in _msgs(r) if m.get("role") == "user"), "")
        if text_to_qid.get(_norm_prompt(first_user)):
            matched += 1
    return matched, len(records)


def _emitted_artifacts(r: dict) -> list[dict]:
    arts = []
    for m in _msgs(r):
        if m.get("role") != "assistant":
            continue
        for blob in _TOOL_CALL_RE.findall(str(m.get("content", ""))):
            try:
                tc = json.loads(blob)
            except json.JSONDecodeError:
                continue
            if tc.get("name") != "generate_viz":
                continue
            for spec in (tc.get("arguments") or {}).get("artifacts", []):
                if isinstance(spec, dict):
                    arts.append(spec)
    return arts


def audit_gold(gold_path: Path) -> None:
    rows = _load_jsonl(gold_path)
    n = len(rows)
    # gold↔intent: every intent should have its gold table (chartjs) or graph (mermaid)
    intent_total = chart_intents = graph_intents = 0
    chart_have = graph_have = 0
    # graph by type: how many have edges vs are edgeless (timeline/mindmap)
    g_with_edges = g_edgeless = 0
    table_bad = 0
    for r in rows:
        tables = {str(t.get("intent_id", "")): t for t in (r.get("tables") or [])}
        graphs = {str(g.get("intent_id", "")): g for g in (r.get("graphs") or [])}
        for it in r.get("intents", []):
            intent_total += 1
            hint = it.get("artifact_type_hint", "")
            iid = str(it.get("intent_id", ""))
            if hint.startswith("chartjs_"):
                chart_intents += 1
                if iid in tables and (tables[iid].get("cells")):
                    chart_have += 1
            elif hint.startswith("mermaid_"):
                graph_intents += 1
                if iid in graphs:
                    graph_have += 1
        for t in (r.get("tables") or []):
            cells = t.get("cells") or []
            if not cells or not all(isinstance(c, dict) and "row" in c and "col" in c for c in cells):
                table_bad += 1
        for g in (r.get("graphs") or []):
            if g.get("edges"):
                g_with_edges += 1
            else:
                g_edgeless += 1
    print(f"\n## GOLD AUDIT — {gold_path.name}  (N={n})")
    print(f"  chart intents: {chart_intents:4d}   with populated gold table: {chart_have:4d}  "
          f"({100*chart_have/max(chart_intents,1):.0f}%)  MISSING={chart_intents-chart_have}")
    print(f"  graph intents: {graph_intents:4d}   with gold graph:           {graph_have:4d}  "
          f"({100*graph_have/max(graph_intents,1):.0f}%)  MISSING={graph_intents-graph_have}")
    print(f"  gold graphs: with_edges={g_with_edges}  edgeless(timeline/mindmap)={g_edgeless}  "
          f"-> edge_f1 structurally 0 for {100*g_edgeless/max(g_with_edges+g_edgeless,1):.0f}% of graphs")
    print(f"  malformed gold tables: {table_bad}")


def audit_run(run_name: str, run_dir: Path, runner_path: Path,
              gold_path: Path, sidecar_dir: Path | None) -> None:
    if not run_dir.exists():
        print(f"\n## RUN AUDIT — {run_name}: MISSING DIR {run_dir}")
        return
    records = []
    for b in sorted(run_dir.glob("batch_*.jsonl")):
        records.extend(_load_jsonl(b))
    if not records:
        traj = run_dir / "trajectories.jsonl"
        if traj.exists():
            records = _load_jsonl(traj)
    dataset = _load_jsonl(runner_path) if runner_path.exists() else []
    gold_qids = {g["qid"] for g in _load_jsonl(gold_path)}
    matched, total = _qid_match(records, dataset)

    # sidecar coverage (B6): emitted artifact (viz_type,intent[:60]) -> dsl?
    side_keys = {}
    if sidecar_dir and sidecar_dir.exists():
        for p in sidecar_dir.glob("*.json"):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            side_keys[(d.get("viz_type", ""), str(d.get("intent", ""))[:60])] = bool(d.get("dsl_code"))
    n_art = n_inline = n_side_hit = 0
    for r in records:
        for spec in _emitted_artifacts(r):
            n_art += 1
            if spec.get("dsl_code", "").strip():
                n_inline += 1
            elif side_keys.get((spec.get("viz_type", ""), str(spec.get("intent", ""))[:60])):
                n_side_hit += 1
    dsl_resolved = n_inline + n_side_hit
    print(f"\n## RUN AUDIT — {run_name}  (records={total})")
    print(f"  qid match: {matched}/{total} ({100*matched/max(total,1):.0f}%)  "
          f"runner={runner_path.name}({len(dataset)})  gold_qids={len(gold_qids)}")
    print(f"  emitted artifacts: {n_art}   inline_dsl={n_inline}  sidecar_resolved={n_side_hit}  "
          f"DSL-resolved={dsl_resolved} ({100*dsl_resolved/max(n_art,1):.0f}%)  "
          f"DSL-MISSING={n_art-dsl_resolved} ({100*(n_art-dsl_resolved)/max(n_art,1):.0f}%)")


if __name__ == "__main__":
    gold300 = REPO / "data/gold/pilot_300.jsonl"
    audit_gold(gold300)
    audit_gold(REPO / "data/gold/pilot_50.jsonl")

    runner_eqctx = REPO / "data/queries/pilot_300_eqctx_runner.jsonl"
    runner_plain = REPO / "data/queries/pilot_300_runner.jsonl"
    sc = REPO / "outputs/v0.5_harness/sidecars"
    runs = [
        ("b6_qwen_eqctx_300", runner_eqctx, sc / "b6_qwen_eqctx_300"),
        ("s1_qwen_real_300", runner_plain, None),
        ("b6_deepseek_eqctx_300", runner_eqctx, sc / "b6_deepseek_eqctx_300"),
        ("s1_deepseek_real_300", runner_plain, None),
        ("b6_gpt5_eqctx_300", runner_eqctx, sc / "b6_gpt5_eqctx_300"),
        ("s1_gpt5mini_300", runner_plain, None),
    ]
    for name, runner, sidecar in runs:
        audit_run(name, REPO / "data" / name, runner, gold300, sidecar)
