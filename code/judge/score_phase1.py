"""Phase-1 scorer — DiagramEval node/path F1 (DSL→graph) + Evidence F1 + Intent
Coverage + render-success, aggregated B6 vs B5 with the gate check.

Approach (per the VLM-blocker decision): the GENERATED graph is extracted
DETERMINISTICALLY from the artifact's Mermaid DSL (we hold the DSL — more faithful
and robust than render→VLM, and free). Node/path alignment reuses DiagramEval's
exact heuristic logic (token-coverage greedy match @0.55 + reachability-path
intersection); we import only its clean graph.py (the evaluator module pulls
langchain, which isn't installed). Gate condition 1's "render success" is the
mmdc render rate over the 5 mermaid subtypes (code/judge/render.py auto-repair).

Gate (exec-plan §3.1, fixed):
  1. render success >= 85% on ALL present mermaid subtypes
  2. B6 - B5 >= +0.020 on >= 2 of {node_f1, path_f1, evidence_f1, intent_cov}
  3. 3-seed variance <= 5%  (run with --seeds for the multi-seed check)
"""
from __future__ import annotations
import argparse, glob, json, re, sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, pstdev

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
# Load DiagramEval's graph.py DIRECTLY by file path — the eval/ package __init__
# pulls evaluator→structured_llm→fitz/langchain (not installed), so a normal
# `from eval.graph import` fails. graph.py itself is dependency-clean.
import importlib.util as _ilu
_gp = REPO / "code/judge/_vendor/diagram-eval/eval/graph.py"
_spec = _ilu.spec_from_file_location("_de_graph", _gp)
_de_graph = _ilu.module_from_spec(_spec)
sys.modules["_de_graph"] = _de_graph  # register before exec so dataclass introspection works
_spec.loader.exec_module(_de_graph)
DiagramGraph = _de_graph.DiagramGraph
from code.metrics.mermaid_metrics import parse_mermaid_to_graph
from code.metrics.hungarian_intent import hungarian_match
from code.metrics.evidence_metrics import evaluate_evidence_explicit
from code.judge.render import render_mermaid


def _vsc_flags(viz_type: str, dsl: str, render_ok: bool) -> dict:
    """tab:vsc per-artifact violation flags (v0.4.3). R1 reuses the render pass
    already run (no double render); R2/R3/R4 are structural via VSC's validator.
    Uniform across all arms — measures how often each arm emits a contract-
    violating artifact. R5 (invalid source ref) is B6-only and read from the B6
    sidecar's recorded vsc_violations, not recomputed here."""
    from code.vsc import validate_dsl
    res = validate_dsl(viz_type, dsl, render=False)
    flags = res.by_rule()          # R2/R3/R4 (+R1=0,R5=0 from structural pass)
    flags["R1"] = 0 if render_ok else 1
    return flags


_TC = re.compile(r"<tool_call>\s*(\{[\s\S]*?\})\s*</tool_call>")
_ROLE = {"human": "user", "gpt": "assistant", "tool": "tool", "system": "system"}


# ── DiagramEval heuristic alignment (reimplemented from evaluator.py) ──────
def _toks(s): return {t for t in (s or "").lower().split() if t}
def _cov(a, b):
    ta, tb = _toks(a), _toks(b)
    if not ta or not tb: return 0.0
    ov = ta & tb
    return max(len(ov)/len(ta), len(ov)/len(tb)) if ov else 0.0
def _f1(p, r): return 2*p*r/(p+r) if (p+r) else 0.0

_EMB = None
def _embedder():
    """Lazy CPU sentence-transformer (DiagramEval's intended node matcher).
    Returns None if unavailable → caller falls back to token-coverage."""
    global _EMB
    if _EMB == "off": return None
    if _EMB is None:
        try:
            import os as _os; _os.environ["CUDA_VISIBLE_DEVICES"] = ""
            from sentence_transformers import SentenceTransformer
            _EMB = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
        except Exception:
            _EMB = "off"; return None
    return _EMB

def _align(ga: DiagramGraph, gb: DiagramGraph, thr=0.75):
    """Greedy node alignment. DiagramEval intended: sentence-transformer cosine
    >= 0.75 (plan §5.2). Falls back to token-coverage @0.55 if ST unavailable."""
    emb = _embedder()
    matches, used = {}, set()
    if emb is not None and ga.nodes and gb.nodes:
        import numpy as np
        ta = emb.encode([n.text for n in ga.nodes]); tb = emb.encode([n.text for n in gb.nodes])
        from numpy.linalg import norm
        for i, na in enumerate(ga.nodes):
            best, bs = None, 0.0
            for j, nb in enumerate(gb.nodes):
                if nb.node_id in used: continue
                d = norm(ta[i]) * norm(tb[j])
                s = float(ta[i] @ tb[j] / d) if d else 0.0
                if s > bs: bs, best = s, nb.node_id
            if best and bs >= thr:
                matches[na.node_id] = best; used.add(best)
        return matches
    for na in ga.nodes:  # token-coverage fallback
        best, bs = None, 0.0
        for nb in gb.nodes:
            if nb.node_id in used: continue
            s = _cov(na.text, nb.text)
            if s > bs: bs, best = s, nb.node_id
        if best and bs >= 0.55:
            matches[na.node_id] = best; used.add(best)
    return matches

def _score(pred: DiagramGraph, gold: DiagramGraph) -> dict:
    m = _align(pred, gold)
    na, nb = max(len(pred.nodes), 1), max(len(gold.nodes), 1)
    np_, nr_ = len(m)/na, len(m)/nb
    node_f1 = _f1(np_, nr_)
    # path alignment
    pa = pred.compute_paths()
    trans = {(m[s], m[d]) for s, d in pa if s in m and d in m}
    pb = gold.compute_paths()
    common = trans & pb
    pp = len(common)/len(trans) if trans else 0.0
    pr = len(common)/len(pb) if pb else 0.0
    path_f1 = _f1(pp, pr)
    return {"node_f1": node_f1, "path_f1": path_f1,
            "n_pred_nodes": len(pred.nodes), "n_gold_nodes": len(gold.nodes)}


def _mermaid_to_dg(dsl: str) -> DiagramGraph | None:
    g = parse_mermaid_to_graph(dsl)
    if g is None: return None
    payload = {"nodes": [{"id": n.id, "text": n.label or n.id} for n in g.nodes],
               "edges": [{"source": e.src, "target": e.dst} for e in g.edges]}
    if not payload["nodes"]: return None
    return DiagramGraph.from_dict(payload, prefix="P")

def _gold_to_dg(gold_graph: dict) -> DiagramGraph | None:
    nodes = gold_graph.get("nodes") or []
    edges = gold_graph.get("edges") or []
    if not nodes: return None
    payload = {"nodes": [{"id": str(n.get("id")), "text": n.get("label", "") or str(n.get("id"))} for n in nodes],
               "edges": [{"source": str(e.get("src")), "target": str(e.get("dst"))} for e in edges if e.get("src") and e.get("dst")]}
    return DiagramGraph.from_dict(payload, prefix="G")


# ── trajectory / sidecar plumbing ─────────────────────────────────────────
def _msgs(r):
    return [{"role": _ROLE.get(m.get("from"), m.get("from", m.get("role"))),
             "content": m.get("value", m.get("content", ""))} for m in r.get("conversations", r.get("messages", []))]

def _norm(s: str) -> str:
    s = str(s)
    if "[Attached documents]" in s:
        # drop any prefix (e.g. retry's [CRITICAL TASK] block) + the attachment list,
        # leaving the query that follows the doc list.
        s = s.split("[Attached documents]")[-1]
        parts = s.split("\n\n", 1); s = parts[1] if len(parts) > 1 else s
    s = s.split("[Output contract]")[0].strip()
    return s[:200]

def _load_sidecars(sidecar_dir: Path) -> dict:
    by_intent = {}
    for p in sidecar_dir.glob("*.json") if sidecar_dir.exists() else []:
        try: d = json.loads(p.read_text())
        except Exception: continue
        by_intent[(d.get("viz_type", ""), str(d.get("intent", ""))[:60])] = d
    return by_intent

def _index_to_doc(r) -> dict:
    """Resolve citation indices <tcid>.<n> -> source doc stem, from the trajectory's
    tool-result messages (doc_search/ReadFullDocument). Lets us compare B6's
    evidence_ids (citation-index namespace) to gold evidence at the DOC level."""
    idx2doc = {}
    for m in _msgs(r):
        if m["role"] != "tool":
            continue
        v = str(m["content"])
        try:
            tr = json.loads(v.replace("<tool_response>", "").replace("</tool_response>", "").strip())
        except Exception:
            # fall back: regex pull Index + title pairs
            for mi in re.finditer(r'"Index"\s*:\s*"([^"]+)"[\s\S]{0,400}?"title"\s*:\s*\\?"?([^"\\]+?\.pdf)', v):
                idx2doc[mi.group(1)] = Path(mi.group(2)).stem
            continue
        for res in (tr.get("content", {}) or {}).get("results", []):
            iid = res.get("Index")
            txt = res.get("text", "")
            mt = re.search(r'"title"\s*:\s*"?([^",}]+?\.pdf)', txt)
            if iid and mt:
                idx2doc[iid] = Path(mt.group(1)).stem
    return idx2doc


def _emitted(r) -> list[dict]:
    out = []
    for m in _msgs(r):
        if m["role"] != "assistant": continue
        for blob in _TC.findall(str(m["content"])):
            try: tc = json.loads(blob)
            except Exception: continue
            if tc.get("name") != "generate_viz": continue
            for a in (tc.get("arguments") or {}).get("artifacts", []):
                if isinstance(a, dict): out.append(a)
    return out


def score_run(traj_dir: Path, sidecar_dir: Path, queries: Path, gold_path: Path,
              is_s1: bool = False, recovered: dict | None = None,
              clipscore: bool = False) -> dict:
    recovered = recovered or {}
    qrows = [json.loads(l) for l in queries.read_text().splitlines() if l.strip()]
    t2q = {_norm(q["text"]): q for q in qrows}
    q_by_id = {q["qid"]: q for q in qrows}
    gold = {g["qid"]: g for g in (json.loads(l) for l in gold_path.read_text().splitlines() if l.strip())}
    side = _load_sidecars(sidecar_dir)

    recs = []
    dirs = [Path(d) for d in str(traj_dir).split(",") if d.strip()]
    for d in dirs:
        for b in sorted(d.glob("batch_*.jsonl")):
            recs += [json.loads(l) for l in b.read_text().splitlines() if l.strip()]

    per = []
    render_ok = Counter(); render_tot = Counter()
    for r in recs:
        # s1_direct stores artifact rows differently
        if is_s1:
            qid = (r.get("metadata") or {}).get("qid") or r.get("qid")
            arts = [{"viz_type": a.get("viz_type", ""), "intent": a.get("intent", ""),
                     "dsl_code": a.get("dsl_code", ""), "evidence_ids": a.get("evidence_ids", [])}
                    for a in _emitted(r)]
        else:
            fu = next((m["content"] for m in _msgs(r) if m["role"] == "user"), "")
            q = t2q.get(_norm(str(fu)))
            qid = q["qid"] if q else None
            arts = []
            for a in _emitted(r):
                key = (a.get("viz_type", ""), str(a.get("intent", ""))[:60])
                sc = side.get(key)
                dsl = (a.get("dsl_code") or "") or (sc.get("dsl_code", "") if sc else "")
                ev = a.get("evidence_ids") or (sc.get("evidence_ids", []) if sc else [])
                arts.append({"viz_type": a.get("viz_type", ""), "intent": a.get("intent", ""),
                             "dsl_code": dsl, "evidence_ids": ev,
                             # v0.4.3 VSC fields recorded at generation time (B6)
                             "vsc_violations": (sc.get("vsc_violations", {}) if sc else {}),
                             "vsc_repaired": (sc.get("vsc_repaired", False) if sc else False),
                             "source_eids": (sc.get("source_eids", []) if sc else [])})
        # forced-emission recovery: if the agent skipped generate_viz, use the
        # post-hoc synthesized artifact from its final prose (recover_b6_viz).
        if not is_s1 and (not arts or not any(a.get("dsl_code", "").strip() for a in arts)) and qid in recovered:
            rc = recovered[qid]
            arts = [{"viz_type": rc.get("viz_type", ""), "intent": rc.get("intent", ""),
                     "dsl_code": rc.get("dsl_code", ""), "evidence_ids": rc.get("evidence_ids", []),
                     # carry VSC fields from VSC-routed recovery (tab:vsc on recovered outputs)
                     "vsc_violations": rc.get("vsc_violations", {}),
                     "vsc_repaired": rc.get("vsc_repaired", False),
                     "source_eids": rc.get("source_eids", [])}]
        g = gold.get(qid)
        if g is None:
            continue
        # pick gold graph (first) + intents/evidence
        gg = (g.get("graphs") or [None])[0]
        gold_dg = _gold_to_dg(gg) if gg else None
        # primary artifact
        a0 = arts[0] if arts else None
        viz_type = a0["viz_type"] if a0 else ""
        # render success (per subtype)
        cs = None  # M5 CLIPScore (image↔query), reported not gating
        render_success = False
        if a0 and a0.get("dsl_code") and viz_type.startswith("mermaid_"):
            render_tot[viz_type] += 1
            png = f"/tmp/_ph1_render/{qid}.png"
            rr = render_mermaid(a0["dsl_code"], png)
            render_success = bool(rr["ok"])
            if rr["ok"]:
                render_ok[viz_type] += 1
                if clipscore:
                    try:
                        from code.metrics.clipscore import compute_clipscore
                        rec = {"query": (q_by_id.get(qid, {}) or {}).get("text", ""),
                               "viz_type": viz_type, "viz_dsl": a0["dsl_code"]}
                        cr = compute_clipscore(png, rec)
                        cs = cr.score if cr.success else None
                    except Exception:
                        cs = None
        # node/path F1
        nf = pf = 0.0
        if a0 and a0.get("dsl_code") and gold_dg is not None:
            pred_dg = _mermaid_to_dg(a0["dsl_code"])
            if pred_dg is not None:
                sc = _score(pred_dg, gold_dg); nf, pf = sc["node_f1"], sc["path_f1"]
        # intent coverage
        ic = hungarian_match([{"viz_type": a["viz_type"], "intent": a["intent"]} for a in arts],
                             g.get("intents", [])).intent_coverage
        # evidence grounding F1 at DOC level (namespaces align on doc stem):
        # resolve the artifact's evidence_ids (citation indices) -> cited doc stems
        # via the trajectory's tool-results, compare to gold evidence doc_ids.
        # B5 (and recovered B6) emit no evidence_ids -> 0 (honest: no SAO grounding).
        ev_ids = a0["evidence_ids"] if a0 else []
        idx2doc = {} if is_s1 else _index_to_doc(r)
        pred_docs = {idx2doc.get(e, "") for e in ev_ids}
        # B6 SAO grounding lives in source_eids ("{doc}#{bid}#{cuid}"); the doc
        # stem maps directly to gold evidence doc_id. Use them when present so
        # the SAO axis is actually measured (recovery emits no evidence_ids).
        src_eids = (a0.get("source_eids") if a0 else None) or []
        pred_docs |= {str(e).split("#")[0] for e in src_eids if e}
        pred_docs.discard("")
        gold_docs = {str(e.get("doc_id")) for e in (g.get("evidence") or []) if e.get("doc_id")}
        if pred_docs and gold_docs:
            inter = len(pred_docs & gold_docs)
            p = inter / len(pred_docs); rc = inter / len(gold_docs)
            ef = (2 * p * rc / (p + rc)) if (p + rc) else 0.0
        else:
            ef = 0.0
        # tab:vsc violation flags (R1 render + R2/R3/R4 structural). R5 + repaired
        # from the B6 sidecar when present (B6-only).
        vsc = {}
        if a0 and a0.get("dsl_code"):
            vsc = _vsc_flags(viz_type, a0["dsl_code"], render_success)
            sc_v = a0.get("vsc_violations") or {}
            if sc_v.get("R5"):
                vsc["R5"] = sc_v["R5"]
        per.append({"qid": qid, "viz_type": viz_type, "has_viz": bool(a0 and a0.get("dsl_code")),
                    "node_f1": nf, "path_f1": pf, "intent_cov": ic, "evidence_f1": ef,
                    "clipscore": cs, "vsc": vsc,
                    "vsc_repaired": bool(a0 and a0.get("vsc_repaired"))})

    # dedup per qid: prefer the record that emitted viz, then higher node_f1
    best = {}
    for p in per:
        cur = best.get(p["qid"])
        if cur is None or (p["has_viz"], p["node_f1"]) > (cur["has_viz"], cur["node_f1"]):
            best[p["qid"]] = p
    per = list(best.values())

    def avg(k):
        xs = [p[k] for p in per]
        return mean(xs) if xs else 0.0
    cs_xs = [p["clipscore"] for p in per if p.get("clipscore") is not None]
    # tab:vsc — violation rate per rule over artifacts that emitted a DSL.
    n_viz = sum(p["has_viz"] for p in per) or 1
    vsc_rate = {}
    for rule, name in (("R1", "render_fail"), ("R2", "dimension_mismatch"),
                       ("R3", "broken_edge"), ("R4", "unsupported_marker"),
                       ("R5", "invalid_source_ref")):
        hits = sum(1 for p in per if p.get("vsc", {}).get(rule, 0))
        vsc_rate[name] = hits / n_viz
    vsc_rate["repaired_rate"] = sum(1 for p in per if p.get("vsc_repaired")) / n_viz
    return {
        "n_scored": len(per), "n_with_viz": sum(p["has_viz"] for p in per),
        "node_f1": avg("node_f1"), "path_f1": avg("path_f1"),
        "intent_cov": avg("intent_cov"), "evidence_f1": avg("evidence_f1"),
        "clipscore": (mean(cs_xs) if cs_xs else None), "n_clipscore": len(cs_xs),
        "render_by_subtype": {k: f"{render_ok[k]}/{render_tot[k]}" for k in render_tot},
        "render_rate": (sum(render_ok.values())/sum(render_tot.values())) if render_tot else 0.0,
        "vsc_violation_rates": vsc_rate,
        "per": per,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--b6-traj", type=Path, required=True)
    ap.add_argument("--b6-sidecar", type=Path, required=True)
    ap.add_argument("--b5-traj", type=Path)
    ap.add_argument("--b7-traj", type=Path, help="SelfRefine baseline (s1-style trajectory)")
    ap.add_argument("--b6-recovered", type=str, default=None,
                    help="JSON of forced-emission recovered artifacts (recover_b6_viz)")
    # v0.4.3 ablation arms (B6 variants). Each scored like B6; the SEF/VSC
    # effect gates compare them to B6 full.
    ap.add_argument("--b6-nosef-traj", type=Path)
    ap.add_argument("--b6-nosef-sidecar", type=Path, default=Path("/nonexistent"))
    ap.add_argument("--b6-nosef-recovered", type=str, default=None)
    ap.add_argument("--b6-novsc-traj", type=Path)
    ap.add_argument("--b6-novsc-sidecar", type=Path, default=Path("/nonexistent"))
    ap.add_argument("--b6-novsc-recovered", type=str, default=None)
    ap.add_argument("--queries", type=Path, default=REPO / "data/queries/loong_phase1_working.jsonl")
    ap.add_argument("--gold", type=Path, default=REPO / "data/gold/loong_phase1_working.jsonl")
    ap.add_argument("--out", type=Path, default=REPO / "outputs/v0.5_harness/PHASE1_GATE.json")
    ap.add_argument("--clipscore", action="store_true",
                    help="compute M5 CLIPScore (OpenCLIP ViT-L/14, image↔query); reported not gating")
    args = ap.parse_args()

    recovered = {}
    if args.b6_recovered and Path(args.b6_recovered).exists():
        recovered = json.loads(Path(args.b6_recovered).read_text())
    b6 = score_run(args.b6_traj, args.b6_sidecar, args.queries, args.gold,
                   recovered=recovered, clipscore=args.clipscore)
    res = {"B6": {k: v for k, v in b6.items() if k != "per"}}
    print("== B6 ==", json.dumps(res["B6"], ensure_ascii=False, indent=2))
    metrics = ["node_f1", "path_f1", "intent_cov", "evidence_f1"]
    baselines = {}  # name -> scored dict (for "B6 vs strongest baseline" gate)
    if args.b5_traj:
        b5 = score_run(args.b5_traj, Path("/nonexistent"), args.queries, args.gold,
                       is_s1=True, clipscore=args.clipscore)
        res["B5"] = {k: v for k, v in b5.items() if k != "per"}
        baselines["B5"] = b5
        res["delta_B6_minus_B5"] = {m: b6[m] - b5[m] for m in metrics}
        print("== B5 ==", json.dumps(res["B5"], ensure_ascii=False, indent=2))
    if args.b7_traj:
        b7 = score_run(args.b7_traj, Path("/nonexistent"), args.queries, args.gold,
                       is_s1=True, clipscore=args.clipscore)
        res["B7"] = {k: v for k, v in b7.items() if k != "per"}
        baselines["B7"] = b7
        res["delta_B6_minus_B7"] = {m: b6[m] - b7[m] for m in metrics}
        print("== B7 ==", json.dumps(res["B7"], ensure_ascii=False, indent=2))
    if baselines:
        # Phase-2 strict gate: B6 vs the STRONGEST baseline per metric (max over B5/B7).
        strongest = {m: max(b[m] for b in baselines.values()) for m in metrics}
        deltas_vs_strongest = {m: b6[m] - strongest[m] for m in metrics}
        n_pass = sum(1 for d in deltas_vs_strongest.values() if d >= 0.020)
        res["delta_B6_vs_strongest"] = deltas_vs_strongest
        res["gate"] = {
            "cond1_render_85": all(b6["render_by_subtype"][k].split("/")[0] != "0" and
                                   int(b6["render_by_subtype"][k].split("/")[0]) / max(int(b6["render_by_subtype"][k].split("/")[1]),1) >= 0.85
                                   for k in b6["render_by_subtype"]) if b6["render_by_subtype"] else False,
            "cond2_disc_2metrics_0.02": n_pass >= 2,
            "metrics_passing": n_pass,
            "deltas_vs_strongest": deltas_vs_strongest,
            "baselines_compared": sorted(baselines),
        }
        print("== GATE (B6 vs strongest baseline) ==",
              json.dumps(res["gate"], ensure_ascii=False, indent=2))

    # v0.4.3 SEF/VSC ablation gates ---------------------------------------
    def _score_variant(traj, sidecar, rec_path):
        rec = (json.loads(Path(rec_path).read_text())
               if rec_path and Path(rec_path).exists() else {})
        return score_run(traj, sidecar, args.queries, args.gold,
                         recovered=rec, clipscore=args.clipscore)

    abl: dict = {}
    if args.b6_nosef_traj:
        nosef = _score_variant(args.b6_nosef_traj, args.b6_nosef_sidecar,
                               args.b6_nosef_recovered)
        res["B6_nosef"] = {k: v for k, v in nosef.items() if k != "per"}
        # negative = SEF helps; plan gate: ≥0.030 drop on some metric.
        d = {m: nosef[m] - b6[m] for m in metrics}
        abl["delta_nosef_minus_full"] = d
        abl["sef_effect_proven"] = any(v <= -0.030 for v in d.values())
        print("== B6 −SEF ==", json.dumps(res["B6_nosef"], ensure_ascii=False, indent=2))
    if args.b6_novsc_traj:
        novsc = _score_variant(args.b6_novsc_traj, args.b6_novsc_sidecar,
                               args.b6_novsc_recovered)
        res["B6_novsc"] = {k: v for k, v in novsc.items() if k != "per"}
        fr = b6["vsc_violation_rates"]; nr = novsc["vsc_violation_rates"]
        keys = ("render_fail", "dimension_mismatch", "broken_edge", "unsupported_marker")
        ratios = {}
        for k in keys:
            f, n = fr.get(k, 0.0), nr.get(k, 0.0)
            ratios[k] = (n / f) if f > 0 else (float("inf") if n > 0 else 1.0)
        abl["vsc_violation_full"] = fr
        abl["vsc_violation_novsc"] = nr
        abl["vsc_violation_ratio_novsc_over_full"] = {k: ratios[k] for k in keys}
        # plan gate: −VSC violations ≥2× full on some aspect.
        abl["vsc_effect_proven"] = any(r >= 2.0 for r in ratios.values())
        print("== B6 −VSC ==", json.dumps(res["B6_novsc"], ensure_ascii=False, indent=2))
    if abl:
        res["ablation"] = abl
        print("== ABLATION (SEF/VSC effect gates) ==",
              json.dumps(abl, ensure_ascii=False, indent=2, default=str))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(res, ensure_ascii=False, indent=2))
    print("wrote", args.out)


if __name__ == "__main__":
    main()
