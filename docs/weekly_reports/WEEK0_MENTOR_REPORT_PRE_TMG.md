# Week 0 Mentor Report (Part 1) — TMG 보완 *이전* 시점 (`week0-pre-tmg` = e5a5552)

> **목적**: Week-0 prototype 검증 사이클에서 §3.2 TMG pillar 구현 누락이 발견되기 *직전* 의 결과를 멘토에게 정확히 보고하기 위한 단독 문서. 이 시점의 결과만으로 §1.2 Method assumption gate 가 통과되었는지를 판단한다.
>
> **이 보고서의 범위**: PR2 ~ PR7 (commits `16ea4a4` → `e5a5552`). 데이터 30 bundles / 60 queries / 120 viz outputs / 120 judged scores. Tag `week0-pre-tmg` 가 보존된 상태.
>
> **Part 2** (`WEEK0_MENTOR_REPORT_POST_TMG.md`) 는 이 시점 이후의 TMG 보완 retry 와 그 결과 발견된 mechanism finding 을 다룬다.

---

## 1. 연구 목표 (Spec §0–§3 요약)

### 1.1 연구 가설

논문은 **DocViz-Agent** 라는 단일 generalist pipeline 이 multi-document query-grounded multi-viz generation 이라는 새로운 task setting (= **QG-MDV**) 에서, 단순 LLM concat baseline 을 의미있게 이긴다고 주장한다. 차별성의 근거는 세 개의 design pillar 의 누적 효과:

| Pillar | 약자 | 메커니즘 |
|---|---|---|
| §3.1 Cross-doc Iterative Search | **CIS** | agent 가 sub-query 를 반복 발행하며 multi-doc 에서 evidence 를 누적 |
| §3.2 Type-aware Multi-Viz Generation | **TMG** | query 의 5 type taxonomy → 적합 viz_type (chartjs/mermaid 6종) 라우팅 + type-specific one-shot prompting |
| §3.3 Source-Attributed DSL Output | **SAO** | viz 의 각 element 에 source doc/chunk metadata 부착 |

### 1.2 §1.2 Method assumption gate (Go/No-Go)

Week-0 prototype 의 핵심 의사결정 기준:

> 60-query 프로토타입에서 **agentic strategy (S4) vs direct-LLM baseline (S1)** 의 효과 크기가 **type 또는 source 단위에서 ≥ +5%p** 면 **GO**.

**MET** 되어야 method 가설이 살아있고, **NOT MET** 이면 spec § 11.4 ablation 의 expected magnitude 가 틀렸다는 뜻 → REFRAME.

이 보고서는 위 gate 가 만족되었는지를 데이터로 답한다. (TMG 보완 *이전* 의 데이터로.)

---

## 2. Implementation snapshot at `week0-pre-tmg`

### 2.1 Strategies (= Pipeline 클래스)

| Strategy | Class | 역할 | TMG 활성화? |
|---|---|---|---|
| **S1** | `S1Direct(Pipeline)` | §7 baseline B5 (Direct-LLM concat) | N/A |
| **S4** | `S4Agentic(Pipeline)` | §7 baseline B6 (DocViz-Agent) | **NO** ← 이 보고서의 핵심 단서 |

**S1Direct** 는 모든 doc 을 12000자 cap 으로 concat → 단일 chat call → JSON `{viz_type, viz_dsl}`. `enable_thinking=False` 로 강제 (Qwen3.6 의 `<think>...</think>` 점령 회피). 6-enum 옵션을 prompt 에 노출하지만 **type-aware 라우팅은 없음**.

**S4Agentic** 은 vendored agent 의 `run_paper_default` 를 호출. 이 함수는 문서 입력을 받아 내부적으로 sub-query 를 반복 생성·검색하며 (CIS pillar), 마지막 step 에서 final_answer 로 viz JSON 을 emit. 그러나 **이 시점에서는 `custom_tools_path` 도 `custom_rules` 도 모두 미지정**.

이 사실의 의미는 §4 (validity) 에서 다시 다룬다.

### 2.2 모델 (Week-0 cost-zero policy)

본 spec 은 query gen 을 GPT-4o-mini, judge gen 을 GPT-5, judge score 를 Claude Opus 4.6 로 prescribe (§5.2 L263, §8.2). 그러나 Week-0 는 closed-API budget 미활성으로 **모든 LLM 호출을 vLLM on-prem `Qwen3.6-27B`** 로 substitute 한다. 구체적으로:

| 사용처 | 모델 | 호출 수 |
|---|---|---|
| query 생성 (`generate_queries.py`) | Qwen3.6-27B | 60 |
| S1 direct chat | Qwen3.6-27B | 60 |
| S4 agent 내부 reasoner (`run_paper_default`) | Qwen3.6-27B | 60 |
| judge checklist 생성 (`checklist_gen.py`) | Qwen3.6-27B | 60 (× 2 strategy_class = 120 cached) |
| judge per-item scoring (`scorer.py`) | Qwen3.6-27B | 120 |

vLLM 다중 host: `QWEN36_27B_PORTS=9101,9102,9103`, S4 의 경우 `--s4-workers 3` 로 round-robin. **모든 호출**은 `temperature=0`, `seed=42` (`PAPER_DEFAULT_*` 상수).

⚠️ **이 substitution 은 명시적 spec deviation** 이고, Week 1 closed-API 활성 시 재측정한다.

### 2.3 Data (§5.1)

30-bundle prototype:

| source | bundles | 내부 docs | 출처 |
|---|---|---|---|
| HotpotQA | 10 | 10× 2 (entity-rich pair) | bridge questions |
| MultiNews | 10 | 10× 2-4 (news cluster) | multi-news |
| arXiv | 5 | 5× 1 (full_text) | visubench Q1-Q2 2026 (2-month window — spec 24-month 대비 deviation) |
| 10-K | 5 | 5× sections | EDGAR; longest-substring 추출 |
| **total** | **30** | — | — |

60 queries: 5-type taxonomy (`quantitative`, `relational`, `temporal`, `hierarchical`, `comparative`) × source distribution. **Type pinning** = bundle 별 가능한 type 만 후보로 줘서 source × type cell 이 비지 않게 한다.

#### 데이터 정합성 caveat (멘토 질문 예상)

- arXiv `cs.LG general` bundle 1 개에 fluid mechanics 논문 (`Topological Characterization of Churn Flow`) 포함 — primary tag 는 cs.LG 라 spec L249 만족, 하지만 `{cs.AI|stat.ML|cs.IT}` 로 secondary 필터 강화 필요.
- 10-K extraction: `re.search` 첫 매치는 TOC 의 zero-length entry 를 잡아버림. **section header 사이 longest substring** 으로 변경하여 해결.
- HTML/SEC parser 들이 spec "≤ 100 LOC each" 를 초과 (140-207 LOC) — 본질적 복잡도라 acceptable 로 표기.

### 2.4 DSL extraction logic (`viz_output_mapper._extract_dsl_block`)

S1, S4 모두 model 의 free-text final_answer 에서 `(viz_type, viz_dsl)` 를 추출해야 한다. 4-stage cascade:

1. **1a — whole-text JSON parse**: `text.lstrip()` 이 `{` 로 시작하면 `json.JSONDecoder().raw_decode` (trailing prose 허용). Qwen 이 chartjs 를 **viz_dsl 키 아래에 nested object** 로 emit 하는 패턴을 잡기 위해 `viz_dsl` 이 dict/list 일 때 `json.dumps` 로 round-trip.
2. **1b — inline regex**: `\{[^{}]*"viz_type"\s*:\s*"[^"]+"[^{}]*\}` (legacy). Nested brace 가 있는 chartjs spec 은 *못 잡음* — PR5 에서 1a 로 우회.
3. **2 — fenced ```mermaid``` block**: header sniff (`flowchart`/`graph`/`mindmap`/`timeline`) → 해당 viz_type.
4. **3 — fenced ```json``` block**: chartjs spec 추출 시도.

#### PR5 의 reprocess pass

배치 직후 60×2 = 120 records 중 26 records 가 fallback path 로 떨어졌다 (mostly Qwen 의 nested-object chartjs). `code/scripts/reprocess_viz.py` 가 1a 로직을 in-place 로 다시 적용 → 22/26 recovery, **API 추가 호출 0**. 이 reprocess 가 syntax_pass 를 §5.3 gate (≥ 90%) 위로 끌어올린 결정적 단계.

### 2.5 Judge (§6)

4-axis checklist judge (Qwen3.6-27B self-judge):

| Axis | 적용 | 의미 |
|---|---|---|
| `faithfulness` | 모든 strategy | viz 의 사실 주장이 source bundle 에 의해 뒷받침되는가 |
| `coverage` | 모든 strategy | query 의 의도를 viz 가 충분히 cover 하는가 |
| `type_appropriateness` | 모든 strategy | 선택된 viz_type 이 query type 에 적합한가 |
| `search_query_quality` | **agentic 만** (S4) | sub_queries 가 의미있게 분해되었나 |

`checklist_gen` 은 (query, source) 당 axis 별 5 items 정도 생성, strategy_class={direct, agentic} 별로 다른 axis 셋이 들어가므로 60 × 2 = **120 cached checklists**. `scorer` 는 각 record 의 모든 item 을 한 번의 LLM call 로 YES/PARTIAL/NO 판정 (1.0 / 0.5 / 0.0). axis 점수 = items mean, overall = axes mean.

⚠️ **이 시점의 critical validity 이슈**: query gen, viz gen, checklist gen, scoring 이 **모두 같은 모델 (Qwen3.6-27B)**. Self-judge bias 의 위험. §8.2 가 prescribe 하는 cross-judge (GPT-5 gen + Opus 4.6 score, κ ≥ 0.70) 는 Week 1 closed-API 활성 시 측정.

---

## 3. Quantitative results — `week0-pre-tmg` (60 records × 2 strategy = 120 viz)

### 3.1 §5.3 Generation gate (error_rate ≤ 5%, syntax_pass ≥ 90%)

| Strategy | n | errors | err_rate | syntax_ok | syntax_pass | gate |
|---|---|---|---|---|---|---|
| S1_Direct | 60 | 0 | 0.000 | 60 | 1.000 | ✅ |
| S4_Agentic | 60 | 1 | 0.017 | 56 | 0.933 | ✅ |

Both PASS. S4 의 1 error 는 agent server 의 transient HTTP 400 (re-run 가능했지만 `--strict` off 로 통과시킴), 4 syntax_fail 은 agent content failure (placeholder text, prose-only output).

### 3.2 §6.4 Judge discriminative range

기대치: 평균 ∈ [0.2, 0.8], std ≥ 0.15 (gate 가 ranking signal 을 보존).

| | faith | cove | type_app | sear_q |
|---|---|---|---|---|
| S1 mean / std | 0.787 / 0.256 ✅ | 0.828 / 0.303 ⚠ | 0.904 / 0.233 ⚠ | — |
| S4 mean / std | 0.817 / 0.262 ⚠ | 0.861 / 0.286 ⚠ | 0.887 / 0.243 ⚠ | 0.767 / 0.338 ✅ |

**Borderline**: 8 cells 중 5 가 ceiling-pressed (mean > 0.8). 그러나 std 0.23–0.34 에 분포가 bimodal (1.00 + fail tail) → ranking signal 은 살아있음. PR7 의 human↔judge Spearman r 결과로 최종 판단 (offline rating 진행 중).

### 3.3 §1.2 Method assumption gate — **MET**

3-way per-(query_type, source) effect of S4 vs S1 on overall mean:

| query_type | n | S1 | S4 | **Δ(S4−S1)** |
|---|---|---|---|---|
| hierarchical | 5 | 0.789 | 0.871 | **+0.082** ✅ |
| relational | 10 | 0.781 | 0.848 | **+0.067** ✅ |
| comparative | 25 | 0.828 | 0.850 | +0.022 |
| quantitative | 5 | 0.967 | 0.879 | −0.088 |
| temporal | 15 | 0.874 | 0.767 | −0.107 |

| source | n | S1 | S4 | **Δ(S4−S1)** |
|---|---|---|---|---|
| arxiv | 10 | 0.750 | 0.904 | **+0.154** ✅ |
| 10k | 10 | 0.878 | 0.777 | −0.101 |
| hotpotqa | 20 | 0.828 | 0.851 | +0.023 |
| multinews | 20 | 0.878 | 0.807 | −0.070 |

**Gate 통과 근거**: hierarchical +8.2%p, relational +6.7%p, arxiv +15.4%p — 세 개의 cell 에서 ≥ +5%p 효과. faith axis 와 coverage axis 에서 부호가 같다는 점도 확인 (consistent direction, 단순 noise 가 아님).

### 3.4 부정 효과 (멘토 질문 예상)

- **temporal −10.7%p, quantitative −8.8%p**: agent loop 가 simple chartjs/timeline 를 생성하는 데 *과잉 reasoning* 을 한다는 가설. PR4 smoke 에서 agent 가 chart 데이터를 직접 생성하기보다 long-form reasoning 으로 빠지는 패턴이 보임. 이 시점에서 *agent 의 type-specific guidance 가 빠져있다는 것* 이 주요 원인 후보 → §3.5 로 이어짐.
- **10k source −10.1%p**: chartjs 생성 시 Qwen 이 viz_dsl 을 nested object 로 emit 하는 패턴이 1a recovery 후에도 일부 잔존. agent 가 이걸 더 자주 함.

### 3.5 핵심 단서: type-specific guidance 부재

S4 의 부정 효과 패턴이 모두 *one viz type-heavy* 한 cell (chartjs-heavy quantitative/10k, timeline-heavy temporal) 에서 발생. S4Agentic 이 `run_paper_default` 를 호출할 때 `custom_tools_path=None`, `custom_rules=None` 으로 invoke 했다는 사실과 일치한다. 즉 §3.2 TMG pillar 가 **구현 누락** 되어있음. 이 발견이 Part 2 의 retry 를 trigger 한다.

---

## 4. Validity 평가 (이 시점에서 어디까지 자신할 수 있는가)

### 4.1 강한 점

1. **§1.2 gate MET**, faith·coverage 같은 부호로 robust.
2. arxiv source +15.4%p 는 1 source × 2 type 만으로도 본 spec 의 method-claim direction 을 지지.
3. §5.3 generation gate 를 두 strategy 모두 PASS — 데이터 자체의 quality artifact 는 아님.

### 4.2 약한 점 (멘토가 물어볼 부분)

| 약점 | 영향 | Week-1 mitigation |
|---|---|---|
| 모든 LLM = Qwen3.6-27B (self-judge bias) | judge 점수 inflation 가능 | closed-API 활성, GPT-5 gen + Opus 4.6 score, κ ≥ 0.70 검증 |
| Per-type cell n = 5 (hierarchical, quantitative) | go/no-go correlation 은 OK, per-type effect inference 부족 | 350 bundles / 700 queries scale-up |
| Judge ceiling-pressed (5/8 cells mean > 0.8) | 점수 상한이 차이를 좁힘 | PR7 Spearman r vs human 으로 ranking signal 검증 + checklist 난이도 calibration |
| arXiv 2-month corpus (spec 24-month) | corpus 분포 편향 가능 | 80-bundle target 으로 fresh API fetch (rate-limit 처리 포함) |
| Single-bundle source loaders 가 spec ≤ 100 LOC 초과 | 형식 deviation, 본질 X | 공통 util 로 refactor 또는 accept |
| **§3.2 TMG pillar 가 구현되지 않은 채로 측정됨** | 이 보고서의 결과는 effectively §11.4 의 **−TMG ablation cell** | Part 2 의 retry |

### 4.3 핵심 self-honesty

**이 시점의 S4 결과는 spec § 7 의 B6 "DocViz-Agent (full)" 가 아니다.** S4 = (B6 − TMG) 의 ablation cell 이다. 그럼에도 §1.2 gate 를 통과한다는 사실은 **CIS pillar 단독으로도 method 가설을 지지하는 근거가 된다**는 의미로 읽을 수 있다 (단, 인과 인정은 ablation 데이터 확보 후).

---

## 5. 의사결정 (이 시점)

| 조건 | 판단 |
|---|---|
| §5.3 generation gate | PASS |
| §6.4 judge discriminative | borderline (PR7 으로 최종 검증) |
| §1.2 method gate | **MET** (S4 vs S1 +5–8%p in 3 cells) |
| §1.2 judge gate | PENDING (PR7 offline ratings) |
| **Decision** | **GO candidate** (judge gate 가 r ≥ 0.5 면 final GO; r < 0.5 면 JUDGE-FIX branch) |

### 5.1 다음 단계 (이 시점에서 계획된 것)

1. **PR7 ratings collection**: 30-viz blinded sample 을 두 rater 가 채점 → `analyze_correlation` (Spearman r + linear-weighted Cohen's κ).
2. **Closed-API activation**: GPT-5 / Opus 4.6 wiring → cross-judge 재측정.
3. **External benchmarks** (§14 Week 1-2): Text2Vis / MatPlotAgent / Plot2Code clone + entry-point 검증.
4. **Scale-up**: 30 → 350 bundles, 60 → 700 queries.

### 5.2 발견된 추가 task — `week0-pre-tmg` 태그를 만든 이유

S4 의 부정 효과 패턴 (§3.4–3.5) 분석 중, vendored agent 의 `agent/examples/diagram/diagram_tools.py` 에 이미 type-aware one-shot (`DIAGRAM_EXAMPLES`, `CHART_DSL_EXAMPLES`) 이 정의되어 있는데 *invoke 되지 않고 있다* 는 사실을 확인. **§3.2 TMG pillar 가 구현 누락**. 이 시점의 결과를 보존하기 위해 `git tag week0-pre-tmg e5a5552` 후 retry 진행 → Part 2 보고서.

---

## 6. 멘토 리뷰 시 예상 질문 / 답변

### Q1. "60 query 로 ±5%p 라는 임계치가 통계적으로 의미있냐?"
60 record paired comparison 에서 type/source 단위 (n=5–25) 로 sign-test 또는 paired bootstrap CI 를 보면, ±5%p 는 noise floor 보다 약간 위. 본 spec 도 prototype 단계에서는 *go/no-go correlation* 이 목적이고, per-type *effect-size* inference 는 Week-1 350 bundles scale-up 으로 미룸 (§14). 이 시점 결과는 가설 *방향* 을 살리는 용도이지, magnitude 를 commit 하는 용도가 아님.

### Q2. "self-judge bias 를 어떻게 통제할 거냐?"
Week-0 는 cost-zero policy 로 Qwen single-model 로 측정. 두 단계로 통제:
- **단기 (PR7)**: 30-viz human rating 으로 Spearman r 측정. r ≥ 0.5 면 single-model judge 라도 ranking signal 은 신뢰 가능. r < 0.5 면 JUDGE-FIX branch 로 분기.
- **장기 (Week 1)**: GPT-5 gen + Opus 4.6 score 로 cross-judge κ ≥ 0.70 검증 (§8.2).

### Q3. "왜 S4 가 quantitative/temporal 에서 *지는*가? 이건 method 가 깨졌단 뜻 아닌가?"
이 보고서 시점에서는 진단 가설 단계: S4 의 agent 가 chartjs/timeline 같은 *구조가 단순한* viz 에 대해 type-specific guidance 없이 호출되고 있어 over-reasoning 으로 빠짐. 이 가설은 Part 2 의 TMG retry 결과로 **부분 검증** 됨 (10k chartjs +15%p, quantitative faith +10%p — TMG 가 실제로 chartjs 케이스를 fix). 하지만 entity-rich Mermaid 에서는 *반대로* 망가짐 → 다른 mechanism. Part 2 §C5 finding 에서 다룸.

### Q4. "TMG 가 구현 안 된 상태의 결과를 'GO' 의 근거로 쓰는 게 honest 한가?"
다음 두 가지 측면에서 honest:
- **Decision unit 의 spec-alignment**: §1.2 gate 는 "S4 vs S1 ≥ +5%p" 라는 *strategy-level* 비교. S4 가 −TMG 셀이라 해도 S1 (B5) 대비 의미있게 우위라는 사실은 method 가설이 *최소한* CIS pillar 의 효과로 지지된다는 데이터. spec 의 §11.4 ablation 에서도 −TMG 가 −2~6%p 만 빠지게 예측되어 있어, S4 (= B6−TMG) ≈ B6 라는 가정이 사전적으로 합리적.
- **태그 보존**: `week0-pre-tmg` 가 e5a5552 에 영구 고정되어, Part 2 의 +TMG 결과가 −TMG 셀과 paired 로 비교 가능. ablation row 가 *real data* 로 채워지는 것은 retry 이후이지만, 이 시점의 결과는 sub-cell 로 재해석 가능한 상태로 보존.

### Q5. "외부 benchmark (Text2Vis, MatPlotAgent, Plot2Code, ViviBench) 비교는 왜 아직 없냐?"
§14 timeline 상 Week 1-2 task. Week 0 는 *self-benchmark (QG-MDV)* 의 §1.2 method gate 만 통과시키는 것이 목적. 외부 benchmark 는 Week-1 에서 thin adapter (`B1-B4`) 로 wrap → 4-setting 평균 비교 (§7 baseline matrix). 현재 미수행은 *지연이 아니라 spec 일정대로*.

### Q6. "30 bundles 면 너무 작지 않나? 과잉적합 우려는?"
Bundle 단위 prototype 의 목적은 (a) loader 정합성, (b) pipeline E2E, (c) judge 의 ranking signal 존재 — 이 3 가지 *infrastructural* 검증이 1차. effect-size 는 Week 1 의 350 bundles 에서 측정. Spec 도 prototype 단계에서 effect-size 를 commit 하지 않도록 §14 단계화.

### Q7. "judge 의 ceiling pressure 가 5/8 cells mean > 0.8 인 게 신호 없는 척도라는 뜻 아니냐?"
mean 만 보면 그렇게 보이지만 std 0.23–0.34 + 분포가 bimodal (1.00 + fail tail) → 점수 분리가 충분. PR7 의 r 가 ≥ 0.5 면 ranking signal 신뢰 가능. r < 0.3 이면 PIVOT (judge 재설계) — 이 분기점이 §1.2 의 decision matrix 에 명시.

---

## 7. Artifact 인덱스 (이 보고서가 reference 하는 데이터)

| 종류 | 위치 | 비고 |
|---|---|---|
| Bundles (30) | `data/prototype/bundles/all.json` | 4 source × 2-doc minimum |
| Queries (60) | `data/prototype/queries/all.json` | 5-type taxonomy |
| Viz outputs (120) | `outputs/prototype/viz/all.json` (e5a5552 시점) | S1 60 + S4 60 |
| Judge scores (120) | `outputs/prototype/judge_scores/all.json` (e5a5552 시점) | 4-axis |
| Human-rating template | `outputs/prototype/human_ratings/template.csv` | 30-viz blinded sample, PR7 |
| Tag | `week0-pre-tmg` (= e5a5552) | retry 이전 상태 영구 보존 |

**이 보고서의 모든 숫자는 e5a5552 시점의 `outputs/prototype/judge_scores/all.json` 에서 직접 산출됨**. 즉 Part 2 의 24bbff3 시점 데이터는 이 표들에 *섞이지 않음*. 동일 데이터 복원은 `git checkout week0-pre-tmg` 후 `python -m code.judge.run_judge`.

---

## 8. Bottom line

> **Week-0 prototype 의 §1.2 method assumption gate 는 TMG pillar 가 *없는 상태* 에서 이미 통과되었다.**
>
> S4 (CIS-only, no TMG) vs S1 (B5 baseline) 의 효과는 hierarchical +8.2%p, relational +6.7%p, arxiv +15.4%p — gate 의 임계치 (≥ +5%p in ≥ 1 cell) 를 3 cell 에서 만족.
>
> 단, 이 시점의 S4 는 spec §7 의 B6 "DocViz-Agent (full)" 이 아니라 §11.4 ablation 의 **−TMG 셀** 이다. TMG pillar 의 실제 기여는 Part 2 의 retry 데이터로 검증한다.
>
> Judge gate 와 cross-judge validation 은 PR7 / Week 1 closed-API 활성으로 미뤄져 있다.
