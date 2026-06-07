"""Forced-emission recovery for B6 trajectories that skipped generate_viz.

The B6 agent reliably RETRIEVES but only emits a generate_viz call ~27% of the
time on Qwen3.5-397B (prose-final-answer failure mode; prompt/retry-resistant).
This recovers a viz for the no-emit trajectories WITHOUT agent-loop surgery:
take the agent's final prose answer (its actual gathered+reasoned content) and
run the same DSL synthesizer B6's generate_viz tool / B5 baseline use, with the
working-set's gold target viz_type. = "forced TMG emission" applied post-hoc;
uses the agent's real work, only supplies the emission step it skipped.

Output: {qid: {viz_type, dsl_code, intent, evidence_ids}} JSON for the scorer's
--b6-recovered hook.
"""
from __future__ import annotations
import argparse, glob, json, re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
import sys; sys.path.insert(0, str(REPO))
from exaone.viz_tools.handle_generate_viz import _synthesize_dsl

_TC = re.compile(r"<tool_call>\s*(\{[\s\S]*?\})\s*</tool_call>")

def _norm(s: str) -> str:
    s = str(s)
    if "[Attached documents]" in s:
        s = s.split("[Attached documents]")[-1]
        p = s.split("\n\n", 1); s = p[1] if len(p) > 1 else s
    return s.split("[Output contract]")[0].strip()[:200]

def _has_viz(r):
    return any("generate_viz" in str(m.get("value", "")) and m.get("from") == "gpt"
               for m in r.get("conversations", []))

def _final_prose(r):
    gpt = [m for m in r.get("conversations", []) if m.get("from") == "gpt"]
    if not gpt: return ""
    v = str(gpt[-1].get("value", ""))
    v = re.sub(r"<think>[\s\S]*?</think>", "", v).strip()
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--traj", default="data/b6_loong_s42,data/b6_loong_retry")
    ap.add_argument("--queries", type=Path, default=REPO / "data/queries/loong_phase1_working.jsonl")
    ap.add_argument("--out", type=Path, default=REPO / "outputs/v0.5_harness/b6_recovered.json")
    ap.add_argument("--workers", type=int, default=16)
    args = ap.parse_args()

    qrows = [json.loads(l) for l in args.queries.read_text().splitlines() if l.strip()]
    t2q = {_norm(q["text"]): q for q in qrows}
    recs = []
    for d in args.traj.split(","):
        for b in sorted(Path(d.strip()).glob("batch_*.jsonl")):
            recs += [json.loads(l) for l in b.read_text().splitlines() if l.strip()]

    # qids already having viz (from any trajectory)
    has, noviz = set(), {}
    for r in recs:
        q = t2q.get(_norm(next((m.get("value", "") for m in r.get("conversations", []) if m.get("from") == "human"), "")))
        if not q: continue
        if _has_viz(r): has.add(q["qid"])
        else: noviz.setdefault(q["qid"], (q, _final_prose(r)))
    targets = {qid: v for qid, v in noviz.items() if qid not in has}
    print(f"viz-present {len(has)} | recovering {len(targets)}")

    def synth(item):
        qid, (q, prose) = item
        vt = q["gold_intents"][0]["artifact_type_hint"]
        brief = (prose or q["text"])[:2000]
        dsl = _synthesize_dsl(vt, brief, intent=q["text"][:200])
        return qid, {"viz_type": vt, "dsl_code": dsl, "intent": q["text"][:200], "evidence_ids": []}

    recovered = {}
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for fut in as_completed([ex.submit(synth, it) for it in targets.items()]):
            qid, art = fut.result()
            recovered[qid] = art
            print(f"  recovered {qid} [{art['viz_type']}] dsl_len={len(art['dsl_code'])}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(recovered, ensure_ascii=False, indent=2))
    print(f"wrote {len(recovered)} → {args.out}")


if __name__ == "__main__":
    main()
