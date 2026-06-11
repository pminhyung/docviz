"""MultiHop-RAG → QG-MDV bundles. Each query's evidence_list spans multiple news
articles; group distinct evidence docs (title→corpus body) into a multi-doc bundle."""
import json, sys, argparse
from pathlib import Path
REPO=Path(__file__).resolve().parents[2]

def load(qf, cf, n):
    queries=json.load(open(qf)); corpus=json.load(open(cf))
    by_title={c['title']:c for c in corpus}
    bundles=[]
    for i,q in enumerate(queries):
        titles=[]
        for e in q.get('evidence_list',[]):
            t=e.get('title')
            if t and t not in titles: titles.append(t)
        docs=[]
        for t in titles:
            c=by_title.get(t)
            if c and c.get('body'):
                docs.append({'doc_id':f"mh_{i}_{abs(hash(t))%100000}", 'title':t, 'content':c['body']})
        if len(docs)>=2:
            qt=q.get('question_type','')
            ct='artifact_planning' if 'comparison' in qt else 'multi_hop'
            bundles.append({'bundle_id':f"multihop_{i}", 'source':'multihop', 'docs':docs[:6],
                            'metadata':{'challenge_type':ct, 'question_type':qt, 'orig_question':q.get('query')}})
        if len(bundles)>=n: break
    return bundles

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--queries", default=str(REPO/"data/_raw/multihoprag/MultiHopRAG.json"))
    ap.add_argument("--corpus", default=str(REPO/"data/_raw/multihoprag/corpus.json"))
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--out", default=str(REPO/"data/bundles/multihop.json"))
    a=ap.parse_args()
    b=load(a.queries,a.corpus,a.n)
    json.dump(b,open(a.out,'w'),ensure_ascii=False,indent=2)
    import statistics as st
    print(f"MultiHop bundles: {len(b)} | 평균 docs {st.mean(len(x['docs']) for x in b):.1f} | challenge: {__import__('collections').Counter(x['metadata']['challenge_type'] for x in b)}")
