"""Multi-source Evidence F1 (C4). Cluster-free: ST embeddings.
- baselines: implicit match — viz node-labels vs bundle doc chunks (cosine>=thr) → pred docs.
- B6: explicit source_eids (doc stems) if present, else implicit.
F1 vs gold evidence doc_ids. Per source.
"""
import json, sys, re, argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from code.judge.score_phase1 import _embedder
import numpy as np
from numpy.linalg import norm

def _nodes_from_dsl(dsl):
    # crude label extraction across mermaid kinds
    labs = re.findall(r'[\["\(\{]+([^\]\)"\}\|>]+)[\]\)"\}]+', dsl or "")
    labs += re.findall(r':\s*([^\n:]+)', dsl or "")
    return [l.strip() for l in labs if 2 <= len(l.strip()) <= 80][:30]

def _bundle_docs(bundles_path, runner_path, queries_path):
    bundles = {b["bundle_id"]: b for b in json.loads(Path(bundles_path).read_text())}
    qid2bid = {}
    # bundle_id may be inline in the query (dochop/multihop) or in a runner file (loong)
    if Path(queries_path).exists():
        for l in Path(queries_path).read_text().splitlines():
            if l.strip():
                q = json.loads(l)
                if q.get("bundle_id"): qid2bid[q["qid"]] = q["bundle_id"]
    if runner_path and Path(runner_path).exists():
        for l in Path(runner_path).read_text().splitlines():
            if l.strip():
                r = json.loads(l); qid2bid.setdefault(r["qid"], r.get("bundle_id"))
    return bundles, qid2bid

def evidence_f1(arm_json, gold_path, bundles, qid2bid, thr=0.75):
    emb = _embedder()
    arts = json.loads(Path(arm_json).read_text())
    gold = {json.loads(l)["qid"]: json.loads(l) for l in Path(gold_path).read_text().splitlines() if l.strip()}
    f1s = []
    for qid, a in arts.items():
        g = gold.get(qid)
        if not g: continue
        gold_docs = {str(e.get("doc_id")) for e in (g.get("evidence") or []) if e.get("doc_id")}
        if not gold_docs: continue
        src_eids = a.get("source_eids") or []
        if src_eids:
            pred = {str(e).split("#")[0] for e in src_eids if e}
        else:
            labs = _nodes_from_dsl(a.get("dsl_code", ""))
            bid = qid2bid.get(qid); docs = (bundles.get(bid) or {}).get("docs") if bid else None
            pred = set()
            if labs and docs:
                viz = emb.encode([" ".join(labs)[:1000]])[0]
                for d in docs:
                    txt = (d.get("content") or "")[:4000]
                    if not txt: continue
                    chunks = [txt[i:i+600] for i in range(0, len(txt), 600)][:8]
                    ch = emb.encode(chunks)
                    if float(((ch @ viz)/(norm(ch,axis=1)*norm(viz)+1e-9)).max()) >= thr:
                        pred.add(str(d.get("doc_id")))
        if pred and gold_docs:
            inter = len(pred & gold_docs); p = inter/len(pred); rc = inter/len(gold_docs)
            f1s.append(2*p*rc/(p+rc) if (p+rc) else 0.0)
        else:
            f1s.append(0.0)
    return sum(f1s)/len(f1s) if f1s else 0.0, len(f1s)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm-json", required=True)
    ap.add_argument("--gold", required=True)
    ap.add_argument("--bundles", required=True)
    ap.add_argument("--queries", required=True)
    ap.add_argument("--runner", default="")
    a = ap.parse_args()
    bundles, qid2bid = _bundle_docs(a.bundles, a.runner, a.queries)
    f1, n = evidence_f1(a.arm_json, a.gold, bundles, qid2bid)
    print(f"evidence_f1={f1:.3f} (n={n})")
