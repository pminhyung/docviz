# §15 Experiment Matrix (v0.3 prototype scale)

> Mirrors amendment §10 with v0.3 prototype-scale numbers + actual
> Phase status (this session).

## 15.1 Per-Layer Generation Counts

| Layer | Setting | # baselines | # records | # generations | Status |
|---|---|---|---|---|---|
| A | QG-MDV in-domain | 7 (B1-B5, B7, B6) | 268 (v0.3 prototype) | 1,876 | Phase 7 ⏰ chained, auto-launching after 10k |
| B-1 | Text2Vis (held-out) | 7 + B8 specialist | 100 | 800 (700 ours + 100 spec) | Phase 5 🟢 data ready, batch pending |
| B-2 | ViviBench (held-out) | 7 + B9 specialist | 101 | 808 | Phase 5 ⚠️ deferred — data not yet public |
| B-3 | Plot2Code (held-out, optional) | 7 + B10 specialist | 50 | 400 | Phase 5 🟡 partial (5-record preflight done) |
| D | Pillar ablation | 4 (B6 Full / −TMG / −SAO / −CIS deferred) | 268 | 1,072 (804 active + 268 deferred) | Phase 8 ⏰ chains after Layer A |
| **Total v0.3 prototype** | | | | **~4,556 active + 268 deferred** | |

## 15.2 Per-Layer Eval

| Layer | Phase-1 judge (active, Qwen) | Phase-2 judge (deferred, closed-API) | Deterministic |
|---|---|---|---|
| A | 4-axis (faith / coverage / type / SQ) | Claude Opus 4.6 scorer + GPT-5 cross-judge | M1 render + M5 CLIPScore + DSL parse |
| B-1 | Text2Vis 4-dim answer-match (Qwen reimpl) | Text2Vis original GPT-4o eval | M1 render + M5 CLIPScore |
| B-2 | ViviBench 4-dim (Qwen reimpl) | ViviBench original eval | (pending data) |
| B-3 | Plot2Code exec-rate (deterministic) + CLIPScore vs target | Plot2Code GPT-4V overall | M1 render + M5 CLIPScore (done in v0.3 5-record preflight) |
| D | 4-axis (Qwen) | (selectively re-judge if Phase 2 budget activates) | M1 + M5 |

## 15.3 Cost Tracking

| Item | v0.3 estimate | Status |
|---|---|---|
| Layer A 1,876 gen (Qwen on-prem) | $0 | chained |
| Layer B 1,500-1,700 gen (Qwen on-prem) | $0 | data ready |
| Layer D 1,072 gen (Qwen on-prem) | $0 | chained after A |
| Phase-1 text judge (Qwen, ~5K records) | $0 | chained |
| Phase-2 closed-API re-judge (headline cells, ~5K records) | ~$1,265 | deferred |
| A5 image judge (Sonnet 700 calls) | ~$50-100 | deferred |
| M5 CLIPScore (~3,500 calls, CPU) | $0 | chained |
| **v0.3 active total** | **$0** | |
| **v0.3 + Phase-2 closed-API** | **~$1,365** | within §10 envelope ($1,720-2,020) |

## 15.4 Wall-Clock Estimate (v0.3 prototype)

| Phase | Sequential | Parallel (workers=3) |
|---|---|---|
| 1 D1 data | ~6h (10k bottleneck) | ~30min (cache fast-path) |
| 2 renderer/parser | ~30min | — |
| 3 queue client | 1-2h | done |
| 4 B1-B4 adapters | 25-30h | done (preflight smokes only) |
| 5 Layer B-1 + B-3 (eval ready) | 6-8h | 2-3h |
| 6 trend gate | ~30min | — |
| 7 Layer A (1,876 gen + judge) | 7-9h | 2-3h |
| 8 Layer D ablation | 3-4h | 1.5h |
| 9 CLIPScore + paired bootstrap | 2-3h | 1h |
| 10 paper draft (this session) | done | — |
| **Total v0.3 active** | | **~8-12h wall-clock from D1 completion** |

10k completion at the time of writing: 16/18 tickers (~29 min elapsed,
~10-12 min ETA). Layer A chain auto-launches after.
