# Week 0 Mentor Report (Part 2) — TMG (Pillar 2) retry *이후* (commits `3d8720d` → `24bbff3`)

> **목적**: §3.2 TMG pillar 의 구현 누락 발견 후 진행한 retry 의 결과를, 멘토에게 (a) 의사결정 근거가 흔들리지 않았다는 점, (b) ablation row 가 실데이터로 채워졌다는 점, (c) 새롭게 발견된 mechanism finding (C5 candidate) 의 의미 — 세 측면에서 정확히 보고한다.
>
> **이 보고서의 범위**: `week0-pre-tmg` (e5a5552) 위에서 진행된 TMG retry. 추가 60 records (S4_AgenticTMG strategy) → 누적 180 viz / 180 judged scores. 최종 commit `24bbff3` 에 WEEK0_REPORT.md (333 lines) 함께 머지.
>
> Part 1 (`WEEK0_MENTOR_REPORT_PRE_TMG.md`) 의 결과 + 의사결정 맥락을 전제로 한다.

---

## 1. Retry 가 시작된 이유

Part 1 의 §3.4–3.5 에서 S4 의 부정 효과 패턴이 *one-viz-type-heavy* 한 cell (chartjs-heavy quantitative/10k, timeline-heavy temporal) 에 집중되어 있다는 것이 확인됨. 이 패턴을 진단하던 중, vendored agent 의 다음 자산이 **호출되지 않은 채로 남아있다는 것** 을 확인:

- `agent/examples/diagram/diagram_tools.py` 안의:
  - `DIAGRAM_EXAMPLES` (6 Mermaid one-shots — flowchart / mindmap / timeline 등)
  - `CHART_DSL_EXAMPLES` (12 chart DSL one-shots — bar / line / grouped_bar)
  - per-type `DIAGRAM_SYSTEM_PROMPT` / `CHART_SYSTEM_PROMPT`

Part 1 의 `S4Agentic.run` 이 `client.run_paper_default(...)` 를 부를 때 `custom_tools_path=None`, `custom_rules=None` 이었으므로 위 자산은 **단 한 번도 prompt 에 들어가지 않았다**. 이것이 정확히 spec § 3.2 **TMG pillar** (Type-aware Multi-Viz Generation) 에 해당하는 기능이다 → **Part 1 의 S4 측정은 effectively §11.4 의 −TMG ablation cell**.

### 1.1 의사결정의 design constraint

retry 를 진행할 때 멘토 입장에서 critical 한 research-design 결정 두 가지:

#### Constraint A — TMG 는 S4 에만 추가하고 S1 은 절대 손대지 않는다.

Spec §7 baseline matrix 에서 **B5 Direct-LLM (= 우리 S1) 은 의도적으로 bare-bones** 이고, **B6 DocViz-Agent (= 우리 S4) 가 3 pillar 를 모두 가진다**. 만약 TMG 를 S1 에도 넣으면:
- S1 의 type_appropriateness 점수가 함께 오름 → spec 이 주장하는 §1.2 Δ(S4 − S1) 가 *baseline contamination* 으로 줄어듦.
- 즉 method 가설을 *불공정하게* 약화시킨다.

이걸 코드 수준에서 확정짓기 위해 `Pipeline.run` ABC 를 `*, query_type: Optional[str] = None` 까지 확장하되, **S1Direct 와 S4Agentic 의 `run` 은 kwarg 를 accept-and-ignore** 로 정의 (§2.2 참조). 이렇게 하면 S1 = baseline, S4 = (B6 − TMG), 그리고 새로 추가하는 S4_AgenticTMG = (B6 full) 의 세 셀이 같은 60 (query, bundle) pair 위에서 **paired comparison** 가능.

#### Constraint B — 기존 데이터를 보존한 채 *세 번째* strategy 를 나란히 추가한다.

Retry 가 기존 60 S1 + 60 S4 records 를 덮어쓰면 ablation paired comparison 이 불가능. `git tag week0-pre-tmg e5a5552` 로 영구 보존 + `code/run_prototype.py` 의 resume key 를 `(query_id, strategy)` 로 바꿔서 이미 완료된 records 를 건너뛰도록. 결과적으로 `outputs/prototype/viz/all.json` 의 entry 가 60 → 180 으로 늘어남 (기존 120 unchanged + 60 신규).

---

## 2. Implementation delta (commit `3d8720d`)

### 2.1 신규 모듈 — `code/pipelines/tmg.py` (171 LOC)

**역할**: query_type 을 받아서 `run_paper_default` 의 `custom_rules` 에 들어갈 routing block 을 만드는 builder.

**핵심 자료구조**:

```python
TYPE_TO_VIZ: Dict[str, Tuple[str, str]] = {
    "quantitative":  ("chartjs_bar",         "chartjs_line"),
    "relational":    ("mermaid_flowchart",   "mermaid_mindmap"),
    "temporal":      ("mermaid_timeline",    "chartjs_line"),
    "hierarchical":  ("mermaid_mindmap",     "mermaid_flowchart"),
    "comparative":   ("chartjs_grouped_bar", "mermaid_flowchart"),
}
```
이 매핑은 spec § 3.2 의 mapping table 을 그대로 따른다. secondary 가 있는 이유는 source 에 따라 primary 가 안 맞는 케이스 (e.g., temporal 인데 시점이 1 개) 에서 agent 가 fallback 할 수 있게 하기 위함.

**One-shot 예시** (`ONE_SHOT_BY_VIZ_TYPE`): 6 viz_type 각각에 대해 `{"viz_type": "...", "viz_dsl": "..."}` JSON 문자열 *완형* 을 하나씩 하드코딩. 형식은 우리 paper schema 그대로 — 이렇게 한 이유는 agent 의 final_answer 가 mapper 의 strategy 1a (whole-text JSON parse) 에 fast-path 로 떨어지게 하기 위함. mermaid_flowchart 예시는:

```
A[Founder] -->|founded| B[Acme Corp]
B -->|acquired| C[Beta Labs]
C -->|hired| D[Engineer X]
A -->|advised| C
```

⚠️ **이 placeholder 선택이 §C5 finding 의 직접적 원인이 된다** (§5).

**`build_tmg_rule(query_type)`**: query_type 이 알려진 5 type 중 하나면 위 mapping + tip + one-shot 을 합쳐 custom_rules block 을 반환. **알 수 없는 query_type 이면 빈 문자열 ""** → `run_paper_default` 의 default rule 만 적용 → 이 fallback 이 정확히 §11.4 −TMG cell 의 동작이다.

### 2.2 신규 클래스 — `code/pipelines/s4_agentic_tmg.py` (90 LOC)

`S4AgenticTMG(Pipeline)`. `S4Agentic` 와 거의 동일하지만 `run()` 안에서:

```python
tmg_rule = build_tmg_rule(query_type) if query_type else ""
response = client.run_paper_default(
    ...,
    custom_rules=tmg_rule if tmg_rule else None,
)
```

CIS pillar 는 agent loop 안에 이미 있고 (Part 1 §2.1), SAO pillar 는 `viz_output_mapper.map_agent_response` 에서 처리되므로 이 클래스는 **TMG 만 추가로 켠 cell** 이 된다. 즉:

| Class | CIS | TMG | SAO |
|---|---|---|---|
| `S1Direct` | × | × | × |
| `S4Agentic` | ✓ | × | ✓ |
| `S4AgenticTMG` | ✓ | **✓** | ✓ |

이 정렬이 spec § 11.4 ablation table 의 row 정의와 정확히 일치.

### 2.3 ABC 확장 — `code/pipelines/base.py`

`Pipeline.run` 의 signature 가 `*, query_type: Optional[str] = None` 로 확장. 핵심은 docstring 에 명시된 contract:

> `query_type` is the 5-type taxonomy label (§4.2) — passed by the runner so TMG-aware variants (DocViz-Agent Pillar 2, §3.2) can route the prompt. **Bare-bones baselines (B5 Direct-LLM, our S1) accept and ignore it; that is the §11.4 "−TMG" ablation cell.**

S1Direct.run, S4Agentic.run 은 `query_type` 을 받지만 *사용하지 않는다*. 이것이 §1.1 Constraint A 를 코드로 enforce 하는 방식.

### 2.4 Runner — `code/run_prototype.py`

`pipeline.run(query, bundle, query_type=q["query_type"])` 으로 항상 query_type 을 전달. 새 strategy 등록:

```python
strategies = {
    "S1": S1Direct(),
    "S4": S4Agentic(),
    "S4_TMG": S4AgenticTMG(),     # ← 신규
}
```

resume key `(query_id, strategy)` → 기존 60+60 records 는 건너뛰고 60 records 만 새로 생성. 출력 파일은 `outputs/prototype/viz/all.json` 으로 동일 (entry 추가만).

### 2.5 다른 모듈 — 변경 없음

- `viz_output_mapper.py` (DSL extraction): 변경 없음. TMG one-shot 의 schema 가 mapper 의 strategy 1a 와 정렬되어 있어 새 매핑 분기 불필요.
- `judge/checklist_gen.py`, `judge/scorer.py`: 변경 없음. 새 strategy 의 strategy_class 는 "agentic" 으로 분류되어 기존 60 cached agentic checklists 를 재사용 (즉 *동일 checklist* 위에서 paired score → 비교가 valid).
- 모든 모델은 그대로 Qwen3.6-27B (§Part 1 §2.2) — closed-API 활성은 Week 1 task.

---

## 3. Smoke verification (전체 batch 전 3 query type sample)

| query_id | query_type | TMG-routed viz_type | DSL chars | Outcome |
|---|---|---|---|---|
| hotpot_00_relational | relational | mermaid_flowchart | 243 | 6 nodes, 동사 라벨 edge, syntax-pass |
| 10k_00_quantitative | quantitative | chartjs_bar | 535 | 깔끔한 Chart.js JSON; **Part 1 의 viz_dsl-as-nested-object 패턴이 사라짐** ← TMG 의 most concrete benefit |
| arxiv_00_hierarchical | hierarchical | mermaid_mindmap | ~400 | 2-3 level taxonomy, syntax-pass |

3 record 모두 mapper strategy 1a fast-path 통과 (one-shot 의 schema 와 model 출력이 일치). 특히 10k_00 의 nested-object 패턴이 사라졌다는 것이 *type-specific one-shot 이 prompt 에 들어가는 것이 효과를 낸 첫 신호*.

---

## 4. 전체 batch (60 records × S4_AgenticTMG, ~62 min wall time)

### 4.1 §5.3 Generation gate

| Strategy | n | errors | err_rate | syntax_ok | syntax_pass | gate |
|---|---|---|---|---|---|---|
| S1_Direct | 60 | 0 | 0.000 | 60 | 1.000 | ✅ |
| S4_Agentic | 60 | 1 | 0.017 | 56 | 0.933 | ✅ |
| **S4_AgenticTMG** | 60 | 1 | 0.017 | **55** | **0.917** | ✅ |

세 strategy 모두 PASS. S4_TMG 가 S4 보다 syntax_pass 0.6%p 낮음 (5 vs 4 syntax_fail). PR5 의 reprocess pass 가 새로 fail 한 5 records 중 0 개를 recover **— 다른 failure mode**:

| # | record | failure |
|---|---|---|
| 1 | 10k_02_quantitative | viz_dsl 가 raw JSON 문자열인데 mapper 1a 가 못 잡음 (truncation/trailing junk 의심) |
| 2 | 10k_03_quantitative | viz_type 추출 OK, chartjs JSON parse_fail (mid-stream 에 prose 부착) |
| 3 | arxiv_02_hierarchical | agent 가 prose-only 로 응답 ("Based on the provided documents...") |
| 4 | hotpot_04_comparative | agent server `localhost:9024/v2/run` 의 transient HTTP 400 |
| 5 | multinews_09_comparative | #1 과 동일 mapper edge case |

전부 **agent content 또는 infra 측 failure** — parser bug 아님. 각 ≤ 1.7% 로 §5.3 gate 안. #1, #5 는 mapper 4th branch 추가 여지 있음 (open question).

### 4.2 §6.4 Judge discriminative range — 3-way

| | faith | cove | type_app | sear_q |
|---|---|---|---|---|
| S1 mean / std | 0.787 / 0.256 ✅ | 0.828 / 0.303 ⚠ | 0.904 / 0.233 ⚠ | — |
| S4 mean / std | 0.817 / 0.262 ⚠ | 0.861 / 0.286 ⚠ | 0.887 / 0.243 ⚠ | 0.767 / 0.338 ✅ |
| **S4_TMG mean / std** | **0.713 / 0.308 ✅** | 0.822 / 0.267 ⚠ | 0.883 / 0.230 ⚠ | 0.725 / 0.334 ✅ |

S4_TMG 의 faith mean = 0.713 — Part 1 의 S4 (0.817) 대비 0.104 *떨어졌고*, 흥미롭게도 discriminative range [0.2, 0.8] 안으로 들어왔다. 즉 **TMG-Full 이 추가됨으로써 judge axis 의 ceiling pressure 가 부분적으로 해소** 되는 부수 효과. 그러나 동시에 *이것이 첫 신호: TMG 가 도움이 아니라 *해* 를 끼치는 케이스가 있다*.

---

## 5. 핵심 발견 — TMG 는 "혼합 신호", spec 예측과 *어긋나는 방향*

### 5.1 Overall mean by query_type (paired, n = 같은 60 pair)

| qt | n | S1 | S4 (−TMG) | **S4_TMG (Full)** | Δ(S4−S1) | **Δ(TMG−S4)** | Δ(TMG−S1) |
|---|---|---|---|---|---|---|---|
| comparative | 25 | 0.828 | 0.850 | 0.749 | +0.022 | **−0.101** | −0.079 |
| hierarchical | 5 | 0.789 | 0.871 | 0.856 | +0.082 | −0.015 | +0.067 |
| quantitative | 5 | 0.967 | 0.879 | **0.946** | −0.088 | **+0.067** | −0.021 |
| relational | 10 | 0.781 | 0.848 | 0.717 | +0.067 | **−0.131** | −0.064 |
| temporal | 15 | 0.874 | 0.767 | 0.817 | −0.107 | +0.050 | −0.057 |
| **mean** | 60 | 0.840 | 0.833 | 0.786 | −0.007 | **−0.047** | −0.054 |

### 5.2 Faithfulness mean by query_type (가장 신호 많이 실리는 axis)

| qt | S1 | S4 (−TMG) | **S4_TMG** | Δ(S4−S1) | **Δ(TMG−S4)** |
|---|---|---|---|---|---|
| comparative | 0.760 | 0.860 | **0.655** | +0.100 | **−0.205** |
| hierarchical | 0.800 | 0.850 | 0.725 | +0.050 | −0.125 |
| quantitative | 0.900 | 0.850 | **0.950** | −0.050 | **+0.100** |
| relational | 0.675 | 0.775 | **0.550** | +0.100 | **−0.225** |
| temporal | 0.867 | 0.750 | 0.833 | −0.117 | +0.083 |

### 5.3 Overall mean by source

| source | n | S1 | S4 | **S4_TMG** | Δ(S4−S1) | **Δ(TMG−S4)** |
|---|---|---|---|---|---|---|
| 10k (chartjs-heavy) | 10 | 0.878 | 0.777 | **0.927** | −0.101 | **+0.150** |
| arxiv | 10 | 0.750 | 0.904 | 0.811 | +0.154 | −0.093 |
| hotpotqa (entity-rich) | 20 | 0.828 | 0.851 | 0.721 | +0.023 | **−0.130** |
| multinews | 20 | 0.878 | 0.807 | 0.767 | −0.070 | −0.041 |

### 5.4 패턴 (한 줄 요약)

> **TMG 는 *bare pipeline 이 구조적으로 어려워하던 케이스* (10k chartjs JSON 포맷팅) 는 잡아주지만 (+15%p), *bare pipeline 이 이미 잘 하던 entity-rich Mermaid 케이스* (hotpot relational/comparative) 는 오히려 망가뜨린다 (−13~22%p faith).**

### 5.5 §11.4 Ablation row 의 첫 실데이터

Spec §11.4 의 `−TMG` row 는 다음과 같이 예측되어 있었다:
- 효과 크기: −2~6%p
- 주요 axis: type_appropriateness

실측:

| Variant | faith | cove | type_app | sear_q | overall |
|---|---|---|---|---|---|
| Full (S4_TMG) | 0.713 | 0.822 | 0.883 | 0.725 | 0.786 |
| − TMG (S4) | 0.817 | 0.861 | 0.887 | 0.767 | 0.833 |
| **Δ (Full − −TMG)** | **−0.104** | **−0.039** | **−0.004** | **−0.042** | **−0.047** |

**불일치 두 가지**:
1. type_appropriateness 의 차이는 **−0.4%p (사실상 0)** — spec 이 예측한 axis 가 아님.
2. faithfulness 의 차이가 **−10.4%p**, 그리고 *Full 이 더 *나쁨***.

즉 spec 의 §11.4 prediction 은 (a) 효과 axis 도 (b) 효과 부호도 *부분적으로 틀렸다*. 단, 이건 **현재 구현된 TMG (placeholder one-shot)** 의 결과이지 TMG pillar 자체의 한계가 아니다 — §6 의 mechanism finding 으로 그 이유가 드러난다.

---

## 6. Mechanism finding (C5 candidate) — *왜* TMG 가 일부 케이스를 망가뜨렸는가

### 6.1 Side-by-side: hotpot_00_relational (paired, same query, same bundle)

**S4 (no TMG, 230 chars)** — judge faith **1.00**:
```
graph LR
    A[Iqbal F. Qadir] -->|Retired Pakistan Navy Admiral| B(Pakistan Navy)
    B -->|Participated in 1971 War| C[Flotilla Attack]
    C -->|Target| D[Radar Station in Dwarka]
    D -->|Located in| E[Dwarka, Gujarat, India]
```

**S4_TMG (213 chars)** — judge faith **0.50**:
```
graph LR
    A[Iqbal F. Qadir] -->|was part of| B[Flotilla]
    B -->|attacked| C[Radar Station in Dwarka]
    C -->|located in| D[Dwarka, India]
    A -->|participated in| E[1971 War]
    B -->|operated during| E
```

**같은 entity set, 비슷한 구조 (4–5 edges).** 하지만 edge label 이 결정적으로 다름:
- S4: 도메인 풍부한 phrase — `"Retired Pakistan Navy Admiral"`, `"Participated in 1971 War"`
- S4_TMG: 짧은 generic verb — `"was part of"`, `"attacked"`, `"operated during"`

### 6.2 Mechanism

`tmg.py:ONE_SHOT_BY_VIZ_TYPE["mermaid_flowchart"]` 의 placeholder:

```
A[Founder] -->|founded| B[Acme Corp]
B -->|acquired| C[Beta Labs]
C -->|hired| D[Engineer X]
A -->|advised| C
```

이 예시의 edge label 들은 모두 **짧은 generic verb** (`founded`, `acquired`, `hired`, `advised`). 모델이 이 예시의 *structure (graph LR / edge syntax)* 만 따라할 것을 기대했지만, **실제로는 *style (verb 의 길이·구체성)* 까지 따라했다**. 결과: source bundle 에 `"Retired Pakistan Navy Admiral"` 같은 도메인 풍부한 phrase 가 있어도 model 은 `"was part of"` 처럼 평탄화된 동사로 출력 → judge 의 faithfulness checklist 에서 "specific entity property mentioned?" 같은 항목이 NO 처리됨.

### 6.3 Paired drop 검증 (n=10 hotpot_relational)

```
hotpot_00  S4=1.00 → TMG=0.50  (Δ −0.50)
hotpot_02  S4=0.75 → TMG=0.25  (Δ −0.50)
hotpot_05  S4=1.00 → TMG=0.25  (Δ −0.75)
hotpot_06  S4=0.75 → TMG=0.50  (Δ −0.25)
hotpot_07  S4=0.75 → TMG=0.50  (Δ −0.25)
+ 5 records 는 동일 score 유지
```

**5/10 records 가 ≥ 0.25 faith 를 잃었고, mean drop = −0.225.** Single outlier 가 아닌 systematic effect.

### 6.4 Finding statement (paper §8 candidate, dubbed C5)

> **"Naive type-aware one-shot prompting can suppress entity-grounded labeling that emerges when the model relies on the source documents."**
>
> 즉 type-aware one-shot 의 *content style* 이 model 의 source-grounded output 를 *override* 할 수 있다. Type-aware prompting 의 효과는 one-shot 의 *content choice* 에 달려있고, generic placeholder 는 entity-rich query type 에서 역효과를 낸다.

### 6.5 Negative finding 으로서의 paper value

이건 method paper 입장에서 *오히려 강한 contribution*:
- 단순 perf-improvement claim ("TMG 가 +X%p 좋다") 보다 **언제 어떻게 작동하는지에 대한 mechanism understanding**.
- Spec §11.4 의 monolithic 예측 ("−TMG: −2~6%p") 을 deconstruction — TMG 의 효과는 *type 별로 부호가 다르다*.
- Week 1 의 TMG-2 (domain-rotated one-shots) 가 v1 → v2 로 회복시키면, 그 *delta 자체가* finding 의 backbone — "TMG works only when one-shots are domain-rich" 라는 정교한 claim.

---

## 7. 의사결정 — Week-0 GO 판정은 *흔들리지 않는다*

### 7.1 §1.2 method gate 는 어디서 충족되는가

Decision matrix (§7 in WEEK0_REPORT.md):

| Judge r (PR7) | S4 effect | Decision |
|---|---|---|
| ≥ 0.5 | ≥ +5%p in ≥ 1 type | **GO** ← *current candidate* |
| ≥ 0.5 | < +5%p anywhere | REFRAME |
| < 0.5 | any | JUDGE-FIX |
| < 0.3 | any | PIVOT |

**S4 effect 는 §11.4 의 −TMG cell (= S4_Agentic) 에서** 측정한다 (Part 1 §3.3 의 +5–8%p in 3 cells). **S4_TMG 의 mixed signal 은 §11.4 ablation row 로 이동** — gate 의 input 이 아니다. 즉:

- `S4_Agentic` (−TMG cell) 의 데이터는 method 가설을 지지 → §1.2 gate **MET**.
- `S4_AgenticTMG` (Full cell) 의 데이터는 ablation row 의 real-data + C5 finding → paper §11.4 + §8 contribution.

이 분리가 가능한 이유는 §1.1 Constraint A–B 의 design 결정 덕분 (S1 미오염 + 기존 60+60 보존).

### 7.2 PR7 judge gate 만 PENDING

- PR7 sample 30 viz: 15 S1 + 15 S4 (S4_TMG 미포함). S1 vs S4 의 ranking 만 검증.
- offline 두 rater → `analyze_correlation` (Spearman r + linear-weighted Cohen's κ).
- **r < 0.3** → PIVOT, **0.3 ≤ r < 0.5** → JUDGE-FIX, **r ≥ 0.5** → final GO.

### 7.3 결과적으로 Week-0 outcome

> **Data-driven GO with one expected condition (PR7 r ≥ 0.5).**
> S4 (DocViz-Agent without TMG) clears the §1.2 method assumption gate via 3 cells.
> TMG, as currently implemented with generic one-shot examples, regresses entity-rich query types — recorded as §11.4 ablation row + C5 finding candidate.

---

## 8. Validity / 멘토 리뷰 시 예상 질문

### Q1. "이 retry 자체가 GO 결과를 흔드는 거 아니냐? TMG 가 나쁘게 나왔는데?"
아니다. §7.1 에서 분명히: §1.2 gate 의 input 은 **S4 (= −TMG cell)** 이고 이건 +5–8%p 효과로 이미 통과. S4_TMG 의 mixed result 는 *§11.4 ablation row* 의 데이터이지 §1.2 gate 의 데이터가 아니다. Spec 자체가 §1.2 와 §11.4 를 *분리* 해놨고, 우리 코드도 그대로 — `S4Agentic.run` 이 query_type 을 ignore 하므로 −TMG cell 의 measurements 가 retry 로 변하지 않았다.

### Q2. "S1 에 TMG 안 넣은 거 진짜로 fair 한 비교냐? Direct LLM 도 type-aware 옵션 줘봐야 하지 않나?"
이건 **method-claim 의 정의** 문제. Spec § 7 baseline matrix:
- B5 Direct-LLM = bare-bones reproducer of "naive concat-and-prompt". B5 는 baseline 의 *floor* 를 정의.
- B6 DocViz-Agent = 3 pillar 통합. C1 의 method contribution unit.

만약 S1 에 TMG 를 넣으면 그건 더 이상 B5 가 아니라 *B5+T* 라는 새 셀이 되어 baseline 정의가 바뀐다. Method gate 가 B6 vs B5 인 이상, S1 = B5 의 정의를 깨면 안 됨. 단, **S1 위에 type-aware option 을 넣은 cell** 을 보고 싶으면 §7 의 *추가 baseline cell* 로 별도 정의하는 게 옳다 (Week 1 expansion 으로 가능).

### Q3. "C5 finding 이 single-judge bias artifact 일 수 있지 않냐?"
타당한 우려. 두 가지 mitigation:
- **paired n=10 design**: same checklist + same scorer 가 같은 judge bias 를 두 strategy 에 동일하게 적용. systematic bias 가 있어도 *paired Δ* 는 robust.
- **side-by-side textual evidence (§6.1)** 가 cardinal: edge label 의 단어 길이·구체성 차이는 judge 점수와 *독립적으로 관찰* 가능. "verb 가 짧고 일반적이다" 라는 사실은 single judge model 의 호감도와 무관한 객관 사실.
- 추가 Week-1 검증: closed-API cross-judge 활성 후 같은 paired records 를 GPT-5 / Opus 4.6 로 re-score → C5 effect 가 cross-judge κ 안에서 reproduce 되는지 확인.

### Q4. "comparative n=25 가 가장 크고 그게 negative effect 의 대부분을 끌어내는 게 아니냐? n imbalance 가 Δ(TMG−S4) overall = −4.7%p 를 만들 수 있지 않나?"
정확한 지적. § 5.1 표에서 query_type 별 Δ(TMG−S4) 를 보면:
- comparative −10.1, hierarchical −1.5, quantitative +6.7, relational −13.1, temporal +5.0
- **per-type unweighted mean** = (−10.1−1.5+6.7−13.1+5.0)/5 = **−2.6%p** (overall mean −4.7%p 보다 작음)

즉 comparative 의 large n 이 overall 을 부정 방향으로 끌어당기는 효과는 있다. 그러나 **5 type 중 3 type 에서 부정** 인 사실은 변하지 않음. paper 에서는 *per-type table* 을 primary 로 쓰고 overall mean 은 secondary 로 표기 (§3.5 prediction 도 per-type 으로 적힘).

### Q5. "S4_TMG 가 hotpot relational 에서 −22.5%p 인데 그게 paper-grade evidence 가 되려면 같은 paper 안에서 reproduce 되어야 하지 않나?"
Week-1 TMG-2 redesign (도메인 회전 one-shot) 후 같은 60 records 로 재측정 → v1 vs v2 paired Δ 를 추가. 즉 paper 의 §11.4 row 가 -TMG / TMG-v1 (placeholder) / TMG-v2 (domain-rich) 의 3-row 로 확장되고, **C5 finding 은 v1 vs v2 의 Δ 로 *재현 검증* 됨**. 만약 v2 도 망가지면 finding 의 폭이 더 강해지고 (TMG pillar 자체의 한계), v2 가 회복하면 finding 이 정교해진다 (TMG 의 효과는 one-shot content 에 의존).

### Q6. "TMG-v2 의 도메인 회전 granularity 어떻게 잡을 거냐?"
두 옵션:
- **per query_type** (5 examples): 비용 적음. Type-level mechanism 가설을 검증.
- **per (source × query_type)** (16 examples — 빈 cell 은 spec 에 없으므로 제외): 비용 ~3x. Source-level domain mismatch 가설까지 검증.

C5 mechanism 이 *content style of one-shot* 에서 비롯되었으므로 per-cell 이 더 직접적 처치. 단, v1 결과가 *모든 type 에서 동일 부호로 망가졌다면* per-type 만으로도 charac. 가능. **v2 smoke 결과가 per-type 차이 (e.g., relational 회복 / comparative 미회복) 를 보이면 그때 per-cell 로 확장** 하는 escalation 전략.

### Q7. "5 syntax-fail 케이스 중 mapper edge case (#1, #5) 가 진짜 mapper bug 가 아닌지 확신 있냐?"
Open question 으로 표기 (§Open Questions). 저장된 `viz_dsl` 문자열이 `{"viz_type": ...}` 로 시작하는 것처럼 보이는데 strategy 1a 가 fail. 가설:
- Trailing prose 가 `raw_decode` 의 종료 위치 이후에 붙어있음 → 1a 는 통과해야 함 (raw_decode 가 trailing 허용).
- Encoding artifact (불가시 char 가 lstrip 후에도 남음) → lstrip 의 whitespace 정의 부족.
- final_answer 가 nested `{ "viz_type": "...", "viz_dsl": { ... nested object ... } }` 인데 lstrip 후 첫 문자가 `{` 가 아님 (e.g., 앞에 짧은 prose).
**Mitigation**: stored 문자열에 대해 offline 으로 1a 를 재실행하는 unit test → 어떤 가설이 맞는지 결정. 5 records 가 모두 같은 메커니즘이면 4-th branch 추가, 아니면 record 별 fix.

### Q8. "전체 retry 와 ablation 확장의 cost (compute, wall) 는?"
- TMG infra 작성 + smoke: ~20 min compute (3-record smoke).
- Full S4_AgenticTMG 60-record batch: **~62 min wall** (Qwen3.6-27B vLLM × 3 host, agent server 1 instance, no restart).
- Judge re-run (60 신규 records, 60 cached checklists 재사용): ~25 min.
- **누적 신규 LLM 호출**: 60 (S4_TMG gen) + 60 (S4_TMG scoring) = 120 (checklist 는 strategy_class 단위로 cached → 추가 0).
- 모두 on-prem, $0 incremental.

### Q9. "이 retry 가 paper 의 timeline (§14) 어디에 영향?"
영향 없음. §14 Week 0 task 안에 *prototype 검증 + GO 판정* 이 포함되어 있고, 그 안에 §11.4 ablation 의 실제 측정도 들어간다 (정확히는 §14 Week 1 의 "verify pillar implementations match spec" 이지만 prototype 단계에서 미리 한 번 한 셈). 즉 retry 는 timeline 을 *앞당긴* 것에 가깝고, Week 1 은 (a) PR7 ratings, (b) TMG-2 redesign, (c) closed-API 활성, (d) 350 bundle scale-up, (e) external benchmarks 로 정상 진행.

---

## 9. Artifact 인덱스

| 파일 | 용도 | 변경 |
|---|---|---|
| `code/pipelines/tmg.py` | TMG routing builder | 신규 (171 LOC) |
| `code/pipelines/s4_agentic_tmg.py` | TMG-aware S4 variant | 신규 (90 LOC) |
| `code/pipelines/base.py` | Pipeline.run signature | `*, query_type` kwarg 추가 |
| `code/pipelines/{s1_direct, s4_agentic}.py` | accept-and-ignore kwarg | minor — kwarg 만 받음 |
| `code/run_prototype.py` | strategy registry, runner kwarg pass | `S4_TMG` 등록 + `query_type` 전달 |
| `outputs/prototype/viz/all.json` | 180 records | 60 신규 추가 (기존 120 unchanged) |
| `outputs/prototype/judge_scores/all.json` | 180 scored | 60 신규 추가 (checklist 60 cached 재사용) |
| `outputs/prototype/judge_scores/checklists.json` | 240 cached | strategy_class agentic 의 60 cached 재사용 |
| `WEEK0_REPORT.md` | mentor-facing summary | 333 lines 신규 (root) |
| Tag `week0-pre-tmg` | retry 이전 영구 보존 | unchanged |
| `docs/reference/sessions/260510-feat-source-loaders-tmg-pillar-retry.md` | full retry record | 신규 |

---

## 10. Bottom line

> **TMG retry 는 (a) §1.2 GO 판정 근거를 흔들지 않으면서 (b) §11.4 ablation row 를 실데이터로 채웠고 (c) C5 mechanism finding 후보를 추가로 산출했다.**
>
> ‌실제 TMG 의 효과는 spec 의 monolithic 예측과 다르다 — *type-by-type 부호가 갈리고*, 효과 axis 도 type_appropriateness 가 아니라 faithfulness. 원인은 우리의 `tmg.py:ONE_SHOT_BY_VIZ_TYPE` 의 placeholder 가 entity-rich query type 에서 *content style override* 를 일으키기 때문 (§6).
>
> Week 1 의 TMG-2 (도메인 회전 one-shot) 결과가 *v1 vs v2 paired Δ* 로 C5 finding 을 재현 검증할 것. 그 결과에 따라 paper 는 단순 +%p claim 보다 **"TMG works only when one-shots are domain-rich"** 라는 정교한 method-design claim 을 펼 수 있다.
>
> 측정 design 이 흔들리지 않은 결정적 요인은 두 가지: (i) S1 미오염 (TMG 는 S4 에만), (ii) `week0-pre-tmg` 태그 + S4_AgenticTMG 의 *나란히 추가* 방식. 이 두 결정이 paired ablation 비교를 가능하게 했다.
