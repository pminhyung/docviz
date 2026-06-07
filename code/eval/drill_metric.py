"""Drill: for b6_qwen_eqctx_300, why are chart_f1/edge_f1 ~0 when DSL+gold exist?
Prints concrete pred-vs-gold for a few matched chart and graph records.
"""
from __future__ import annotations
import json, re, sys
from pathlib import Path
from statistics import mean

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from code.metrics.chart_metrics import parse_chartjs_to_table, evaluate_chartjs
from code.metrics.mermaid_metrics import parse_mermaid_to_graph, evaluate_mermaid

TC = re.compile(r"<tool_call>\s*(\{[\s\S]*?\})\s*</tool_call>")
ROLE = {"human": "user", "gpt": "assistant", "system": "system", "tool": "tool"}

def jl(p): return [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()]
def msgs(r):
    o=[]
    for m in r.get("conversations", []):
        o.append({"role":ROLE.get(m["from"],m["from"]),"content":m.get("value","")} if "from" in m else m)
    return o
def norm(s):
    if "[Attached documents]" in s:
        p=s.split("\n\n",1); s=p[1] if len(p)>1 else s
    s=s.strip(); return s[-220:] if len(s)>220 else s

gold={g["qid"]:g for g in jl(REPO/"data/gold/pilot_300.jsonl")}
dataset=jl(REPO/"data/queries/pilot_300_eqctx_runner.jsonl")
t2q={norm(r.get("prompt","")):r.get("qid") for r in dataset}
sc={}
for p in (REPO/"outputs/v0.5_harness/sidecars/b6_qwen_eqctx_300").glob("*.json"):
    try: d=json.loads(p.read_text())
    except: continue
    sc[(d.get("viz_type",""), str(d.get("intent",""))[:60])]=d.get("dsl_code","")

records=[]
for b in sorted((REPO/"data/b6_qwen_eqctx_300").glob("batch_*.jsonl")): records+=jl(b)

def arts(r):
    out=[]
    for m in msgs(r):
        if m.get("role")!="assistant": continue
        for blob in TC.findall(str(m.get("content",""))):
            try: tc=json.loads(blob)
            except: continue
            if tc.get("name")!="generate_viz": continue
            for spec in (tc.get("arguments") or {}).get("artifacts",[]):
                if not isinstance(spec,dict): continue
                dsl=spec.get("dsl_code","") or sc.get((spec.get("viz_type",""),str(spec.get("intent",""))[:60]),"")
                out.append({"viz_type":spec.get("viz_type",""),"intent":spec.get("intent",""),"dsl_code":dsl})
    return out

chart_shown=graph_shown=0
all_chart=[]; all_edge=[]; all_node=[]
for r in records:
    fu=next((str(m.get("content","")) for m in msgs(r) if m.get("role")=="user"),"")
    qid=t2q.get(norm(fu));  g=gold.get(qid)
    if not g: continue
    tables={str(t.get("intent_id","")):t for t in (g.get("tables") or [])}
    graphs={str(gr.get("intent_id","")):gr for gr in (g.get("graphs") or [])}
    for a in arts(r):
        vt=a["viz_type"]
        if vt.startswith("chartjs_") and tables:
            gt=next(iter(tables.values()))
            res=evaluate_chartjs(a, gt); all_chart.append(res["chart_data_f1"])
            if chart_shown<3 and gt.get("cells"):
                pt=parse_chartjs_to_table(a["dsl_code"])
                print(f"\n=== CHART qid={qid} f1={res['chart_data_f1']:.2f} parse_fail={res['parse_failed']}")
                print("  PRED cells:", [(c.row,c.col,c.value) for c in (pt.cells if pt else [])][:6])
                print("  GOLD cells:", [(c.get('row'),c.get('col'),c.get('value')) for c in gt.get('cells',[])][:6])
                chart_shown+=1
        if vt.startswith("mermaid_") and graphs:
            gg=next(iter(graphs.values()))
            res=evaluate_mermaid(a, gg); all_edge.append(res["edge_f1"]); all_node.append(res["node_f1"])
            if graph_shown<3 and gg.get("edges"):
                pg=parse_mermaid_to_graph(a["dsl_code"])
                print(f"\n=== GRAPH qid={qid} edge_f1={res['edge_f1']:.2f} node_f1={res['node_f1']:.2f} parse_fail={res['parse_failed']}")
                print("  PRED nodes:", [(n.id,n.label) for n in (pg.nodes if pg else [])][:6])
                print("  PRED edges:", [(e.src,e.dst,e.label) for e in (pg.edges if pg else [])][:6])
                print("  GOLD nodes:", [(n.get('id'),n.get('label')) for n in gg.get('nodes',[])][:6])
                print("  GOLD edges:", [(e.get('src'),e.get('dst'),e.get('label')) for e in gg.get('edges',[])][:6])
                graph_shown+=1

print(f"\n## DISTRIBUTION over b6_qwen_eqctx_300")
print(f"  chart_data_f1: n={len(all_chart)} mean={mean(all_chart):.3f} zeros={sum(1 for x in all_chart if x==0)}")
print(f"  edge_f1:       n={len(all_edge)} mean={mean(all_edge):.3f} zeros={sum(1 for x in all_edge if x==0)}")
print(f"  node_f1:       n={len(all_node)} mean={mean(all_node):.3f} zeros={sum(1 for x in all_node if x==0)}")
