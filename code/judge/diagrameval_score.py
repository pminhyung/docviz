"""Real DiagramEval node/path F1 via Qwen-VL — replaces the homegrown DSL-parse.

Qwen3.5-397B IS a VLM. This renders each viz to PNG, has Qwen-VL extract the
graph from the IMAGE (DiagramEval's actual method, human-corr r=0.43), builds the
reference graph from gold, and computes node/path alignment F1 via DiagramEval's
LLM aligner. Distributes across the 7-host Qwen pool; one DiagramEvaluator per
host, round-robin. Output: {qid: {node_f1, path_f1, ok}} cache the scorer reads.

  python code/judge/diagrameval_score.py \
    --recovered outputs/v0.5_harness/rec_full_s42.json \
    --gold data/gold/loong_phase2_working.jsonl \
    --out outputs/v0.5_harness/dgeval_full_s42.json --workers 14
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
_DE = REPO / "code/judge/_vendor/diagram-eval"
# import REPO's `code.judge.render` first (REPO ahead of stdlib `code`)...
sys.path.insert(0, str(REPO))
from code.judge.render import render_mermaid  # noqa: E402
# ...then put diagram-eval first so its top-level `eval`/`utils` win.
sys.path.insert(0, str(_DE))
from eval.evaluator import DiagramEvaluator  # noqa: E402
from eval.graph import DiagramGraph  # noqa: E402

_ALL_HOSTS = [f"10.1.211.{h}" for h in (148, 163, 164, 165, 166, 167, 168)]
# DGEVAL_HOSTS="148,163" restricts the pool; default = all, then health-filtered.
if os.environ.get("DGEVAL_HOSTS"):
    _ALL_HOSTS = [f"10.1.211.{h.strip()}" for h in os.environ["DGEVAL_HOSTS"].split(",")]
HOSTS = list(_ALL_HOSTS)
MODEL = os.environ.get("DGEVAL_MODEL", "Qwen3.5-397B-A17B-FP8")


def _live_hosts(hosts):
    """Keep only hosts whose VISION endpoint actually answers — a dead host (OOM)
    still serves /models but APIConnectionErrors on image calls, and pinning a
    worker thread to it fails every sample. Re-checked at each run start."""
    import base64 as _b64
    import openai as _oai
    png = "/tmp/_dgeval_health.png"
    if not os.path.exists(png):
        try:
            render_mermaid("flowchart TD\n A[X]-->B[Y]", png)
        except Exception:
            pass
    try:
        img = _b64.b64encode(open(png, "rb").read()).decode()
    except Exception:
        return hosts
    live = []
    for h in hosts:
        try:
            c = _oai.OpenAI(base_url=f"http://{h}:8000/v1", api_key="EMPTY", timeout=45)
            c.chat.completions.create(
                model=MODEL, max_tokens=50, temperature=0.6,
                extra_body={"chat_template_kwargs": {"enable_thinking": True}},
                messages=[{"role": "user", "content": [
                    {"type": "text", "text": "ok?"},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img}"}}]}])
            live.append(h)
        except Exception:
            pass
    return live

_CFG_DIR = Path(tempfile.mkdtemp(prefix="dgeval_cfg_"))
_local = threading.local()


def _config_for_host(host: str) -> str:
    """Write a per-host DiagramEval config (api_type=nvidia → OpenAI-compatible)."""
    d = _CFG_DIR / host
    d.mkdir(exist_ok=True)
    (d / "key.yaml").write_text("openai_api_key: EMPTY\n")
    base = dict(api_type="nvidia", model=MODEL, key_file="key.yaml",
                api_key="openai_api_key", base_url=f"http://{host}:8000/v1",
                temperature=0, max_tokens=4000)
    cfg = {"text_graph_extraction": dict(base),
           "image_graph_extraction": dict(base, timeout=120),
           "node_alignment": dict(base)}
    p = d / "cfg.yaml"
    p.write_text(yaml.safe_dump(cfg))
    return str(p)


def _evaluator() -> DiagramEvaluator:
    """One evaluator per worker thread, pinned to a host (round-robin by thread)."""
    ev = getattr(_local, "ev", None)
    if ev is None:
        idx = getattr(_local, "idx", None)
        if idx is None:
            with _IDX_LOCK:
                global _NEXT
                idx = _NEXT % len(HOSTS); _NEXT += 1
            _local.idx = idx
        _local.ev = DiagramEvaluator(_config_for_host(HOSTS[idx]))
        ev = _local.ev
    return ev


_NEXT = 0
_IDX_LOCK = threading.Lock()


def _gold_to_ref(gold_graph: dict) -> DiagramGraph | None:
    nodes = gold_graph.get("nodes") or []
    if not nodes:
        return None
    ref = DiagramGraph(); idmap = {}
    for n in nodes:
        lbl = (n.get("label") or "").strip()
        if lbl:
            idmap[n.get("id")] = ref.add_node(lbl).node_id
    for e in gold_graph.get("edges") or []:
        s, t = idmap.get(e.get("src")), idmap.get(e.get("dst"))
        if s and t:
            ref.add_edge(s, t)
    return ref if list(ref.nodes) else None


def score_one(qid: str, dsl: str, gold_graph: dict) -> dict:
    """Render dsl → Qwen-VL graph extraction → align vs gold → node/path F1."""
    ref = _gold_to_ref(gold_graph)
    if ref is None:
        return {"qid": qid, "node_f1": 0.0, "path_f1": 0.0, "ok": False, "why": "empty_gold"}
    png = f"/tmp/_dgeval/{qid}.png"
    rr = render_mermaid(dsl, png)
    if not rr["ok"]:
        return {"qid": qid, "node_f1": 0.0, "path_f1": 0.0, "ok": False, "why": "render_fail"}
    try:
        res = _evaluator().evaluate(png, ref)
        return {"qid": qid,
                "node_f1": res.node_alignment.scores.f1,
                "path_f1": res.path_alignment.scores.f1,
                "ok": True}
    except Exception as exc:
        return {"qid": qid, "node_f1": 0.0, "path_f1": 0.0, "ok": False,
                "why": f"eval_err:{type(exc).__name__}"}


def _load_dsls(recovered: Path | None, traj: Path | None) -> dict:
    """qid -> dsl. Prefers the recovered artifacts (the scored B6 DSL)."""
    out = {}
    if recovered and recovered.exists():
        for qid, a in json.loads(recovered.read_text()).items():
            if a.get("dsl_code"):
                out[qid] = a["dsl_code"]
    return out


def _load_baseline_dsls(traj: Path, queries: Path) -> dict:
    """qid -> dsl for an s1-style baseline (B5/B7): match each record's human
    message to its query, pull dsl_code from the emitted generate_viz artifact."""
    sys.path.append(str(REPO))
    from code.judge.score_phase1 import _emitted, _norm
    t2q = {_norm(json.loads(l)["text"]): json.loads(l)
           for l in queries.read_text().splitlines() if l.strip()}
    out = {}
    for b in sorted(traj.glob("batch_*.jsonl")):
        for line in b.read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            hu = next((m.get("value", "") for m in r.get("conversations", [])
                       if m.get("from") == "human"), "")
            q = t2q.get(_norm(str(hu)))
            em = _emitted(r)
            if q and em and em[0].get("dsl_code"):
                out[q["qid"]] = em[0]["dsl_code"]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--recovered", type=Path)
    ap.add_argument("--baseline-traj", type=Path, help="s1-style B5/B7 trajectory dir")
    ap.add_argument("--queries", type=Path, default=REPO / "data/queries/loong_phase2_working.jsonl")
    ap.add_argument("--gold", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--workers", type=int, default=14)
    a = ap.parse_args()

    gold = {json.loads(l)["qid"]: json.loads(l)
            for l in a.gold.read_text().splitlines() if l.strip()}
    if a.baseline_traj:
        dsls = _load_baseline_dsls(a.baseline_traj, a.queries)
    else:
        dsls = _load_dsls(a.recovered, None)
    items = [(qid, dsl, (gold.get(qid, {}).get("graphs") or [{}])[0])
             for qid, dsl in dsls.items() if qid in gold]
    global HOSTS
    HOSTS = _live_hosts(HOSTS) or HOSTS
    workers = min(a.workers, max(1, len(HOSTS) * 2))  # ≤2 per live host (avoid OOM)
    print(f"scoring {len(items)} viz via DiagramEval Qwen-VL "
          f"(live hosts {[h.split('.')[-1] for h in HOSTS]}, {workers} workers)")

    results = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(score_one, qid, dsl, gg) for qid, dsl, gg in items]
        for i, f in enumerate(as_completed(futs), 1):
            r = f.result(); results[r["qid"]] = r
            if i % 20 == 0:
                print(f"  {i}/{len(items)}")
    ok = sum(1 for r in results.values() if r["ok"])
    import statistics as st
    nf = st.mean([r["node_f1"] for r in results.values()]) if results else 0
    pf = st.mean([r["path_f1"] for r in results.values()]) if results else 0
    print(f"done: ok {ok}/{len(results)} | node_f1 {nf:.3f} path_f1 {pf:.3f}")
    a.out.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
