"""Score pre-rendered PNGs (B1-B4 baselines output images, not mermaid) via
DiagramEval Qwen-VL — same image→graph extraction, just skip the render step."""
import sys, json, argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from code.judge.diagrameval_score import _evaluator, _gold_to_ref, _live_hosts, HOSTS
import code.judge.diagrameval_score as D

def score_png(qid, png, gold_graph):
    ref = _gold_to_ref(gold_graph)
    if ref is None: return {"qid":qid,"node_f1":0,"path_f1":0,"ok":False,"why":"empty_gold"}
    if not png or not Path(png).exists():
        return {"qid":qid,"node_f1":0,"path_f1":0,"ok":False,"why":"no_render"}
    try:
        r=_evaluator().evaluate(png, ref)
        return {"qid":qid,"node_f1":r.node_alignment.scores.f1,"path_f1":r.path_alignment.scores.f1,"ok":True}
    except Exception as e:
        return {"qid":qid,"node_f1":0,"path_f1":0,"ok":False,"why":f"eval_err:{type(e).__name__}"}

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--baseline-out",type=Path,required=True)  # b{arm}_loong_s42.json
    ap.add_argument("--gold",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    ap.add_argument("--workers",type=int,default=16)
    a=ap.parse_args()
    gold={json.loads(l)["qid"]:json.loads(l) for l in a.gold.read_text().splitlines() if l.strip()}
    arts=json.loads(a.baseline_out.read_text())
    items=[(q,v.get("png",""),(gold.get(q,{}).get("graphs") or [{}])[0]) for q,v in arts.items() if q in gold]
    D.HOSTS=_live_hosts(HOSTS) or HOSTS
    w=min(a.workers,max(1,len(D.HOSTS)*2))
    print(f"scoring {len(items)} PNGs (live {[h.split('.')[-1] for h in D.HOSTS]}, {w} workers)")
    res={}
    with ThreadPoolExecutor(max_workers=w) as ex:
        for i,f in enumerate(as_completed([ex.submit(score_png,q,p,g) for q,p,g in items]),1):
            r=f.result(); res[r["qid"]]=r
            if i%20==0: print(f"  {i}/{len(items)}")
    import statistics as st
    ok=[r for r in res.values() if r["ok"]]
    print(f"done: ok {len(ok)}/{len(res)} | node {st.mean([r['node_f1'] for r in ok]) if ok else 0:.3f} path {st.mean([r['path_f1'] for r in ok]) if ok else 0:.3f}")
    a.out.write_text(json.dumps(res,ensure_ascii=False,indent=2))
