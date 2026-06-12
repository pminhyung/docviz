"""DocHop-QA → QG-MDV bundles. Multi-hop items (used_doc=multi, 2+ pmc_id) become
multi-doc bundles: group context_list passages by pmc_id → one Doc per paper.
Viz queries are generated separately by the querygen pipeline (not DocHop's QA Q)."""
import json, sys, argparse, collections
from pathlib import Path
REPO=Path(__file__).resolve().parents[2]

def load(raw, n, seed=42):
    data=json.load(open(raw))
    multi=[d for d in data if d.get('used_doc')=='multi' and len(set(c.get('pmc_id') for c in d['context_list']))>=2]
    multi.sort(key=lambda d: d['id'])           # deterministic
    bundles=[]
    for d in multi[:n]:
        by=collections.OrderedDict()
        for c in d['context_list']:
            by.setdefault(c['pmc_id'], []).append(c.get('content') or c.get('Raw content') or '')
        docs=[{'doc_id':f"dochop_{d['id']}_{pid}", 'title':pid,
               'content':'\n\n'.join(t for t in txts if t)} for pid,txts in by.items()]
        docs=[x for x in docs if x['content'].strip()]
        if len(docs)>=2:
            bundles.append({'bundle_id':f"dochop_{d['id']}", 'source':'dochop',
                            'docs':docs, 'metadata':{'challenge_type':('artifact_planning' if d.get('hop_type') in ('comparison','bridge_comparison') else 'multi_hop'),'hop_type':d.get('hop_type'),
                            'task_type':d.get('task_type'), 'orig_question':d.get('question')}})
    return bundles

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--raw", default=str(REPO/"data/_raw/dochopqa/[F] DocHopQA_Dataset.json"))
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--out", default=str(REPO/"data/bundles/dochop.json"))
    a=ap.parse_args()
    b=load(a.raw, a.n)
    json.dump(b, open(a.out,'w'), ensure_ascii=False, indent=2)
    import statistics as st
    print(f"DocHop bundles: {len(b)} | 평균 docs/bundle {st.mean(len(x['docs']) for x in b):.1f} | 평균 chars {st.mean(x_len for x_len in (sum(len(d['content']) for d in x['docs']) for x in b)):.0f}")
