"""Aggregate harness measurement → 4-metric paper-table (v0.4.1 §13).

For each run, reads:
  - data/{run_name}/trajectories.jsonl  (or batch_*.jsonl fallback)
  - sidecars dir specified by --sidecars
  - data/gold/pilot_50.jsonl

Computes:
  Chart Data F1, Graph Edge F1, Evidence F1, Intent Coverage
per record + aggregate means.

Output: outputs/v0.5_harness/pilot_results/{run_name}.json + markdown summary.

Usage:
    python -m code.eval.aggregate_pilot \\
        --run-dir data/b6_qwen_pilot \\
        --sidecars outputs/v0.5_harness/sidecars/b6_qwen \\
        --gold data/gold/pilot_50.jsonl \\
        --out outputs/v0.5_harness/pilot_results/b6_qwen.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from code.metrics.chart_metrics import evaluate_chartjs
from code.metrics.mermaid_metrics import evaluate_mermaid
from code.metrics.evidence_metrics import evaluate_evidence_explicit
from code.metrics.hungarian_intent import hungarian_match


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _load_run_records(run_dir: Path) -> list[dict]:
    """Prefer trajectories.jsonl; fall back to concatenated batch_*.jsonl."""
    traj = run_dir / "trajectories.jsonl"
    if traj.exists() and traj.stat().st_size > 0:
        return _load_jsonl(traj)
    rows: list[dict] = []
    for batch in sorted(run_dir.glob("batch_*.jsonl")):
        rows.extend(_load_jsonl(batch))
    return rows


def _qid_from_record(record: dict, dataset_lookup: dict) -> str | None:
    """Recover the qid for a trajectory row by matching prompt to dataset_lookup."""
    idx = record.get("prompt_index")
    if idx is not None and idx in dataset_lookup:
        return dataset_lookup[idx].get("qid")
    # Fallback: match by prompt text
    md = record.get("metadata") or {}
    return md.get("qid")


def _load_sidecars(sidecar_dir: Path) -> dict[str, list[dict]]:
    """Index sidecars by task_id (prefix of filename)."""
    out: dict[str, list[dict]] = defaultdict(list)
    if not sidecar_dir.exists():
        return out
    for p in sorted(sidecar_dir.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        tid = d.get("task_id") or p.stem.split("__a")[0]
        out[tid].append(d)
    return out


def _evaluate_one(query: dict, gold: dict, artifacts: list[dict]) -> dict:
    """Compute the 4 deterministic metrics for one (query, gold, artifacts) trio."""
    # Hungarian intent matching across all artifacts
    gold_intents = gold.get("intents") or query.get("gold_intents", [])
    if not isinstance(gold_intents, list):
        gold_intents = []
    artifact_dicts = [{
        "viz_type": a.get("viz_type", ""),
        "intent": a.get("intent", ""),
        "dsl_code": a.get("dsl_code", ""),
        "evidence_ids": a.get("evidence_ids", []),
    } for a in artifacts]
    hung = hungarian_match(artifact_dicts, gold_intents)

    # For each matched (artifact_i, gold_intent_j): compute chart or graph F1
    chart_f1s: list[float] = []
    graph_f1s: list[float] = []
    evid_f1s: list[float] = []

    gold_tables = gold.get("tables") or []
    gold_graphs = gold.get("graphs") or []
    gold_evidence_ids = [e.get("id") for e in (gold.get("evidence") or []) if e.get("id")]

    for art_idx, gold_idx, cost in hung.matches:
        art = artifact_dicts[art_idx]
        viz_type = art.get("viz_type", "")
        # Pair with the closest gold table/graph by intent_id (defaults to first if no match)
        if viz_type.startswith("chartjs_") and gold_tables:
            # Try matching by intent_id; fallback to first
            gold_intent_id = str(gold_intents[gold_idx].get("intent_id", ""))
            matched_table = next(
                (t for t in gold_tables if str(t.get("intent_id", "")) == gold_intent_id),
                gold_tables[0] if gold_tables else None,
            )
            if matched_table:
                cm = evaluate_chartjs(art, matched_table)
                chart_f1s.append(cm["chart_data_f1"])
        elif viz_type.startswith("mermaid_") and gold_graphs:
            gold_intent_id = str(gold_intents[gold_idx].get("intent_id", ""))
            matched_graph = next(
                (g for g in gold_graphs if str(g.get("intent_id", "")) == gold_intent_id),
                gold_graphs[0] if gold_graphs else None,
            )
            if matched_graph:
                mm = evaluate_mermaid(art, matched_graph)
                graph_f1s.append(mm["edge_f1"])
        # Evidence F1 (explicit only — fast path; implicit needs embedder, P5)
        if art.get("evidence_ids"):
            ev = evaluate_evidence_explicit(art["evidence_ids"], gold_evidence_ids)
            evid_f1s.append(ev.evidence_f1)

    return {
        "intent_coverage": hung.intent_coverage,
        "redundancy_rate": hung.redundancy_rate,
        "n_artifacts": hung.n_artifacts,
        "n_gold_intents": hung.n_gold,
        "chart_data_f1_mean": mean(chart_f1s) if chart_f1s else None,
        "graph_edge_f1_mean": mean(graph_f1s) if graph_f1s else None,
        "evidence_f1_mean": mean(evid_f1s) if evid_f1s else None,
        "n_chart_evaluated": len(chart_f1s),
        "n_graph_evaluated": len(graph_f1s),
        "n_evidence_evaluated": len(evid_f1s),
    }


def aggregate(run_dir: Path, sidecar_dir: Path, gold_path: Path,
              dataset_path: Path, out_path: Path) -> dict:
    records = _load_run_records(run_dir)
    if not records:
        print(f"[aggregate] no records in {run_dir}")
        return {"n_records": 0}
    sidecars = _load_sidecars(sidecar_dir)
    golds = {g["qid"]: g for g in _load_jsonl(gold_path)}
    dataset = _load_jsonl(dataset_path)
    dataset_by_idx = {i: row for i, row in enumerate(dataset)}
    print(f"[aggregate] {len(records)} records, {len(golds)} gold, {len(sidecars)} sidecar groups")

    per_record: list[dict] = []
    for r in records:
        qid = _qid_from_record(r, dataset_by_idx)
        if not qid:
            continue
        gold = golds.get(qid)
        if not gold:
            continue
        # Find this record's task_id via metadata then match sidecars
        md = r.get("metadata") or {}
        task_id = md.get("task_id") or f"task_{r.get('prompt_index', 0)}"
        artifacts = sidecars.get(task_id, [])
        if not artifacts:
            # Try matching by qid in sidecar payload
            for tid, arts in sidecars.items():
                if any(a.get("qid") == qid for a in arts):
                    artifacts = arts
                    break
        # Filter out failed preflights
        artifacts = [a for a in artifacts if a.get("preflight_ok", True)]
        # Attach query info for gold_intent lookup
        query = next((d for d in dataset if d.get("qid") == qid), {})
        result = _evaluate_one(query, gold, artifacts)
        result.update({
            "qid": qid,
            "challenge_type": query.get("challenge_type"),
            "output_type": query.get("output_type"),
            "source": query.get("bundle_id", "?").split("_")[0],
            "n_sidecar_artifacts": len(artifacts),
        })
        per_record.append(result)

    # Aggregate
    def _mean(vals):
        clean = [v for v in vals if v is not None]
        return mean(clean) if clean else None

    summary = {
        "n_records": len(per_record),
        "intent_coverage_mean": _mean(r["intent_coverage"] for r in per_record),
        "chart_data_f1_mean": _mean(r["chart_data_f1_mean"] for r in per_record),
        "graph_edge_f1_mean": _mean(r["graph_edge_f1_mean"] for r in per_record),
        "evidence_f1_mean": _mean(r["evidence_f1_mean"] for r in per_record),
        "by_challenge_type": {},
        "by_source": {},
    }
    by_ct: dict[str, list[dict]] = defaultdict(list)
    by_src: dict[str, list[dict]] = defaultdict(list)
    for r in per_record:
        by_ct[r.get("challenge_type") or "?"].append(r)
        by_src[r.get("source") or "?"].append(r)
    for k, rs in by_ct.items():
        summary["by_challenge_type"][k] = {
            "n": len(rs),
            "intent_coverage": _mean(x["intent_coverage"] for x in rs),
            "chart_data_f1": _mean(x["chart_data_f1_mean"] for x in rs),
            "graph_edge_f1": _mean(x["graph_edge_f1_mean"] for x in rs),
            "evidence_f1": _mean(x["evidence_f1_mean"] for x in rs),
        }
    for k, rs in by_src.items():
        summary["by_source"][k] = {
            "n": len(rs),
            "intent_coverage": _mean(x["intent_coverage"] for x in rs),
            "chart_data_f1": _mean(x["chart_data_f1_mean"] for x in rs),
            "graph_edge_f1": _mean(x["graph_edge_f1_mean"] for x in rs),
            "evidence_f1": _mean(x["evidence_f1_mean"] for x in rs),
        }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({"summary": summary, "per_record": per_record},
                   indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"[aggregate] wrote {out_path}")
    print()
    print(f"=== Summary ({run_dir.name}) ===")
    print(f"n_records: {summary['n_records']}")
    for k in ("intent_coverage_mean", "chart_data_f1_mean",
              "graph_edge_f1_mean", "evidence_f1_mean"):
        v = summary[k]
        print(f"  {k}: {v:.4f}" if v is not None else f"  {k}: (no data)")
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", type=Path, required=True)
    ap.add_argument("--sidecars", type=Path, required=True)
    ap.add_argument("--gold", type=Path, default=Path("data/gold/pilot_50.jsonl"))
    ap.add_argument("--dataset", type=Path,
                    default=Path("data/queries/pilot_50_runner.jsonl"))
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    aggregate(args.run_dir, args.sidecars, args.gold, args.dataset, args.out)
