# Plot2Code V4_consolidated (B6) Held-Out Failure Analysis

Date: 2026-05-13. Sources:
- `outputs/plot2code/viz/all.json` (5 B6 records, qids 00-04)
- `outputs/plot2code/viz/raw.jsonl` (19 in-flight B6 records, qids 05-24; bulk still streaming)
- Combined: **24 B6 records** (bulk targets ~45). The in-flight tail keeps adding records matching
  the same single failure signature (`tokens_out=0, empty final_answer, 3.7 s wall, "agent returned
  empty final_answer"`) and the agent server log confirms upstream `401 Unauthorized` for the
  current window, so conclusions are robust.
- B1 home-turf comparison: `B1_MatPlotAgent` records 00-04 (n=5).
- Agent server log: `/tmp/docviz_logs/agent_server_9037.log` (1.6 MB).
- Sidecar dir (orphaned tool outputs from 400-error records): `/tmp/v4_viz_outputs/`.

Files referenced in fixes:
- `code/pipelines/s4_agentic_tmg.py` (orchestrator)
- `code/adapters/agent_client.py` (HTTP client)
- `code/adapters/viz_output_mapper.py` (mapper)
- `code/agent_tools/generate_viz.py` (custom tool)
- `code/pipelines/tmg.py` (V4_POOL_EXPOSURE_RULE)
- `agent/run_agent_v2.py` (agent loop)
- `agent/api/server.py`, `agent/api/handlers.py`, `agent/api/schemas.py` (FastAPI layer)

---

## Section 1 — Summary table (mode → count → fix → leverage)

| Mode | Count (n=24) | Trigger | Fix | Leverage | Layer-A risk |
|---|---|---|---|---|---|
| **I: HTTP 400 AFTER sidecar write** | 3 (qids 00, 02, 03) | server rejects own response via Pydantic `ValueError` → 400; tool already wrote a valid sidecar | **Fix #1** sidecar-rescue in orchestrator | **HIGHEST (pure bug)** | ~zero — only fires on agent exception + sidecar present |
| **A1: silent 401 (auth)** | ~10 (qids 06-24 majority) | upstream vLLM returns 401, agent loop's `except Exception` masks it as 200 OK + empty `final_answer` | **Fix #2** broaden retry trigger; **Fix #3** auth-failure batch-halt; **Fix #4** server re-raise | **HIGH (infra)** | none — same root cause as Layer A Mode A |
| **A2: silent ConnectError** | ~5 (subset of above) | per-host transient; current `<5 s duration` retry gate misses cases where Setup block exceeds 5 s before the LLM call fails | **Fix #2** | HIGH | adds 1 retry to ≤5 Layer-A records |
| **C: 600 s ReadTimeout** | 3 (qids 09, 13, 17) | server hung; orchestrator's httpx read-timeout fires | server-side per-step timeout | MEDIUM | same Layer-A pattern |
| **R: render reject despite syntax-valid** | 2 of 3 sv=True (qids 01, 05) | model emits mermaid `subgraph + <br/> + style ... fill:` that the renderer chokes on | **Fix #8** stronger styling-strip in tool + post-process | MEDIUM | minor — purely cosmetic strip |
| **T': wrong subtype within feasible set** | 1 (qid 05) | model picks `mermaid_flowchart` for a 2-line plot that should be `chartjs_line` | **Fix #6** clarify use-case hints | MEDIUM | small — hint refinement only |
| **T: taxonomy fundamental limit** | ≥10 across the 50-record bulk (qids 00, 06, 08, 09, 11, 14, 16, ...) | source is 2x2 / 4-subplot / treemap / box-plot grid; none of the 10 enum subtypes can capture multi-panel composition | **none** | **FUNDAMENTAL** | n/a |
| Successful (1 rendered + 2 syntax-valid) | 3 (qids 01, 04, 05) | — | — | — | — |

**Mode A1 vs A2** are two distinct infra modes that the current orchestrator retry treats
identically. Layer-A preflight (2026-05-13) saw ConnectError → 80 % recovery. Plot2Code bulk
launched in an auth-failure window → 0 % recovery, because every host shares one creds.

---

## Section 2 — Per-mode detailed analysis

### Mode I (qids 00, 02, 03) — HTTP 400 after sidecar write. **Highest-leverage bug.**

**Recorded outcome (identical pattern across 3 records)**:
```
viz_type: ""    viz_dsl: ""    syntax_valid: False
errors: ["HTTPStatusError: Client error '400 Bad Request' for url 'http://localhost:9037/v2/run'"]
tokens_in/out: 0 / 0     duration: 57–109 s (real LLM work, not transient)
```

**Agent server log proves the agent DID complete a valid run** (lines 281-389):
```
[Load] Loaded 1 document(s): ['plot2code_00_01_plot2code-instruction-0.json']
[Step 1] Document summary generated (382 chars)
[Step 2] Tool: search
[Step 3] Tool: generate_viz                          ← tool invoked
[Step 4] Final answer generated                      ← final_answer produced
INFO:  - "POST /v2/run HTTP/1.1" 400 Bad Request    ← server rejected its own response
```

**The orphaned sidecars (`/tmp/v4_viz_outputs/v4_consolidated_plot2code_0{0,2,3}_plot2code.json`) contain
clean V4_cons output**:

- qid 00 → 983-byte `mermaid_flowchart` representing the 3-plot Gaussian-noise layout.
- qid 02 → 499-byte `mermaid_flowchart` for the R/plotly two-treemap pipeline.
- qid 03 → 1407-byte `chartjs_line` with the World-population stacked-area data, ALL 5 continents
  × 8 years correctly extracted. **This DSL would pass syntax_valid and render cleanly.**

**Root cause (best inference)**: `agent/api/server.py:191` catches `ValueError` (including Pydantic
`ValidationError`) and returns 400 without a traceback. The most plausible trigger is response-side
Pydantic validation of `RunResponseV2` (`agent/api/schemas.py:211`) — e.g., a `StepReasoning` with
NaN `duration` or missing `step_number` on the `generate_viz` step. **Plot2Code amplifies this to
12.5 % vs Layer A's 2.5 %** likely because Plot2Code is the only source where `n_docs == 1`
consistently — the validation path differs when `inputs_used == 1` and a custom tool was used.

**The orchestrator never recovers the sidecar** because the `HTTPStatusError` raised by
`code/adapters/agent_client.py:290` (`resp.raise_for_status()`) propagates up past the
`_read_viz_sidecar` block at `s4_agentic_tmg.py:252-262`.

**B1 comparison on qids 00, 02, 03**: B1 produced matplotlib code, render_success=True for all. For
qid 03 specifically, B6's sidecar `chartjs_line` is **semantically equivalent within taxonomy** to
B1's matplotlib stacked-area — same continents, same years, same population numbers.

### Mode A1 (≈10 of qids 06-24) — silent 401 auth failure. **Dominant.**

**Recorded outcome (identical across all 15 affected records)**:
```
viz_type: "mermaid_flowchart"   ← mapper fallback artifact, NOT model's choice
viz_dsl: ""    syntax_valid: False
errors: ["agent returned empty final_answer",
         "S4_AgenticTMGv4_consolidated: generate_viz sidecar missing for query_id=...;
          agent likely did not invoke the tool. Final_answer used as fallback."]
tokens_in/out: 0 / 0     duration: 3.75–3.77 s    n_sub_queries: 0
```

The fixed 3.7 s duration is "two agent server calls each ≈0.4 s + 3 s retry sleep" — the Mode A
retry at `s4_agentic_tmg.py:236-243` IS firing (server log shows `[Load]` twice per query_id at
lines 28741/28791, 28830/28868, etc.), but **both calls die in Step 1**:

```
[Error] Agent loop failed: Error code: 401 - {'error': 'Unauthorized'}
openai.AuthenticationError: Error code: 401 - {'error': 'Unauthorized'}
```

**This is cluster-wide auth failure**, not a per-host transient. `_next_reasoner_url()` rotates to a
different host but all hosts share the same vLLM frontend credential (`reasoner_api_key="EMPTY"`
against the auth proxy). The agent server's silent except (`run_agent_v2.py:459`) converts the
hard 401 into 200 OK + empty `final_answer`, hiding the root cause from the orchestrator.

The `mermaid_flowchart` viz_type on these records is a **mapper fallback artifact**
(`viz_output_mapper.py:262`'s `fallback_viz_type="mermaid_flowchart"` on empty extraction). Real
viz_type is unknown — no tool call ever ran.

### Mode A2 (≈5 records) — silent ConnectError + 5 s gate miss

Subset of "empty final_answer + tokens=0" cases where the **server-reported
`total_duration_seconds` > 5.0** (because the `[Setup]` block alone took 5-10 s before the LLM call
failed). The current retry trigger at `s4_agentic_tmg.py:239` requires `< 5.0`, so these slip past
the retry without recovery. The signature is similar to A1 but the failure is per-host transient
ConnectError rather than auth.

### Mode C (qids 09, 13, 17) — 600 s ReadTimeout

```
errors: ["ReadTimeout: timed out"]    duration: 603.5 s    tokens: 0
```

The agent server hung mid-loop, likely on a single upstream LLM call that never returned. The
orchestrator's 600 s httpx read-timeout fires. No sidecar (tool call never reached). Same root cause
as Layer A's 3 Mode-C records.

### Mode R — syntax-valid but renderer rejects

**qid 01** (`mermaid_flowchart`, 577 B):
```
graph TD
    subgraph TopSubplot [Top Subplot: Sine Wave Frequency 2π]
        direction TB
        X1[X-Axis: 0 to 10<br/>Increment: 0.01] -->|Apply sin(x * 2π)| Y1[Y-Values: sin(2πx)]
    end
    [...]
    style TopSubplot fill:#f5f5f5,stroke:#333,stroke-width:1px
```
Renderer rejects: `<br/>` inside subgraph label + `style ... fill:` directive, despite
`generate_viz.py:407-412`'s "avoid styling directives" guidance. The exemplar's syntax-only
intent leaked through.

**qid 05** (`mermaid_flowchart`, 652 B): same pattern: `Start((Origin<br/>0,0))` (parenthesized
node shape `((...))` plus `<br/>`) and `style Legend fill:#ffffff`.

**qid 04** (`chartjs_bar`, 654 B): RENDERED OK. Data `{3:1, 5:4, 8:1, 10:2}` correctly captures the
histogram source "5, 10, 3, 10, 5, 8, 5, 5". True success.

### Mode T' — wrong subtype within a feasible set

**qid 05** is the diagnostic example. Source: "2 lines (straight diagonal + sine curve) on a 6×6
plot." Clean `chartjs_line` fit. Agent chose `mermaid_flowchart` with cute node-shaped endpoints.
The `_VIZ_TYPE_USE_CASES` map in `generate_viz.py:85-96` describes `chartjs_line` as "trend over
ordered axis (time, sequence)" — which doesn't obviously include a 2-curve f(x)/g(x) plot, so the
model defaulted to relational/flowchart.

### Mode T — taxonomy fundamental limit

Mapped from the 16 bundle descriptions we could read:

| qid | Source | 10-enum fit | Lossy? |
|---|---|---|---|
| 00 | line + 2 inset plots | flowchart of layout | yes |
| 01 | 2 stacked subplots (sine 2π/4π) | none can show both axes | yes |
| 02 | 2 R/plotly treemaps side-by-side | mindmap × 2? | yes |
| 03 | stacked area, 5 continents × 8 years | chartjs_line (stacked) | **clean fit** |
| 04 | histogram | chartjs_bar | **clean fit** |
| 05 | 2 lines (straight + sine) | chartjs_line | **clean fit** (model picked flowchart) |
| 06 | 4 wind-barb subplots in 2×2 | none | yes |
| 07 | grouped bar (ggplot diamonds) | chartjs_grouped_bar | **clean fit** |
| 08 | 2 stacked subplots (signal + coherence) | none | yes |
| 09 | 4 subplots (mislabeled ylabels demo) | none | yes |
| 10 | treemap | mindmap | partial |
| 11 | overlaid histogram + rug | chartjs_bar | lossy |
| 12 | Gantt chart | mermaid_timeline | partial |
| 14 | box-plot grid | none directly | yes |
| 15 | scatter w/ 2 marker shapes | chartjs_scatter | clean fit (loses marker shape) |
| 16 | facet bar (Sex × Smoker × Day) | chartjs_grouped_bar | lossy |

**~60 % of Plot2Code targets are intrinsically out of the 10-subtype scope.** With infrastructure
perfectly fixed, the realistic held-out exec_rate ceiling for B6 V4_cons is ~70-75 % vs B1's 100 %.

### Cross-check: B6 vs B1 on qids 00-04 (no Mode T contamination)

| qid | B6 outcome | B6 sidecar | B1 outcome | Honest B6 status after Fix #1 |
|---|---|---|---|---|
| 00 | HTTP 400 | flowchart 983 B (3-plot layout) | render OK | sidecar-recoverable; flowchart-of-layout will pass syntax but be lossy vs B1 |
| 01 | sv=True / render fail | n/a | render OK | needs Fix #8 mermaid-strip → render OK |
| 02 | HTTP 400 | flowchart 499 B (treemap pipeline) | render OK | sidecar-recoverable, lossy |
| 03 | HTTP 400 | **chartjs_line 1407 B (correct data)** | render OK | sidecar-recoverable, clean fit |
| 04 | sv=True + render OK | n/a | render OK | already success |

**With only Fix #1 (sidecar-rescue)**, B6 exec_rate on qids 00-04 jumps from 1/5 (20 %) to 4/5 (80 %)
assuming qids 00/02 syntax-pass on read (highly likely, both are well-formed mermaid graphs)
and qid 03 renders cleanly. Adding Fix #8 makes qid 01 render → 5/5 on the in-domain feasible subset.

---

## Section 3 — Prioritized fix proposals

### Fix #1 — Sidecar-rescue in orchestrator on `HTTPStatusError` / `RuntimeError`

**File**: `code/pipelines/s4_agentic_tmg.py:188-264`.

**Diff sketch**:
```python
# wrap _do_run in try/except so 400/500/network failures don't blow past the sidecar.
response = None; agent_error = None
try:
    response = _do_run(self._reasoner_base_url)
except Exception as e:
    agent_error = f"{type(e).__name__}: {e}"

# existing Mode A retry block — only entered when response is not None
if response is not None and not response.final_answer and response.total_tokens == 0:
    time.sleep(3.0)
    retry_url = _next_reasoner_url()
    try:
        response = _do_run(retry_url)
    except Exception as e:
        agent_error = (agent_error or "") + f" | retry: {type(e).__name__}: {e}"

# sidecar fallback: when BOTH attempts blew up, build VizOutput directly from sidecar
if response is None and self.mode in ("v4_pool", "v4_consolidated"):
    sidecar = _read_viz_sidecar(self.mode, query_id)
    if sidecar:
        return VizOutput(
            viz_dsl=sidecar.get("viz_dsl",""), viz_type=sidecar.get("viz_type",""),
            rendered_image_path="", render_success=False,
            retrieved_chunks=[{"doc_id":"concat","chunk_id":"all","content":"",
                               "source_path": doc_paths[0]}],
            sub_queries=[], source_attribution={}, tokens_in=0, tokens_out=0, cost_usd=0.0,
            errors=[f"{self.name}: agent server raised {agent_error}; recovered viz from sidecar."],
        )
    raise RuntimeError(agent_error or "agent server returned None")

vo = map_agent_response(response, bundle, ...)
# existing v4 sidecar override block (lines 252-262) stays — handles the 200-OK happy path.
```

**Expected recovery**: +3 of 24 (qids 00, 02, 03). Across Layer A, also catches the 1 documented
Mode-D 400. Total ~+4 records across the whole eval.

**Risk to Layer A**: ~zero. New path only activates when an exception was caught AND a sidecar
exists. Happy 200-OK records unchanged.

### Fix #2 — Broaden Mode A retry trigger (drop the `< 5 s` floor)

**File**: `code/pipelines/s4_agentic_tmg.py:236-243`.

**Diff**:
```python
# was: if (not response.final_answer and response.total_tokens == 0 and
#         response.total_duration_seconds < 5.0):
if response.total_tokens == 0 and not response.final_answer:
    time.sleep(3.0)
    retry_url = _next_reasoner_url()
    response = _do_run(retry_url)
```

The `<5.0` floor over-fits Layer-A's transient-ConnectError shape. Plot2Code shows servers exceed
5 s of `[Setup]` even on a 401-first-call run. `tokens_out==0 + empty final_answer` is the only
reliable signal.

**Expected recovery**: in ConnectError mode, ≥80 % (matches preflight). In current auth-failure mode,
0 % (retry hits same auth wall) — combine with Fix #3.

**Risk to Layer A**: +1 retry on ≤5 currently-skipped records; ≤30 s wall-clock overhead.

### Fix #3 — Auth-failure batch-halt (treat 3 consecutive empty-200s as fatal)

**File**: `code/adapters/agent_client.py` — add module-level counter in `AgentClient` / `_post_run`.

**Sketch**:
```python
_CONSECUTIVE_EMPTY_200 = 0
_EMPTY_200_THRESHOLD = 3

def _post_run(self, body):
    ...
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("final_answer","") == "" and payload.get("total_tokens",0) == 0:
        AgentClient._CONSECUTIVE_EMPTY_200 += 1
        if AgentClient._CONSECUTIVE_EMPTY_200 >= _EMPTY_200_THRESHOLD:
            raise RuntimeError(
                "Aborting batch: 3 consecutive empty-final_answer 200 OKs — "
                "likely a cluster-wide auth/connectivity failure. Inspect "
                "/tmp/docviz_logs/agent_server_9037.log and rotate vLLM credentials.")
    else:
        AgentClient._CONSECUTIVE_EMPTY_200 = 0
    return ...
```

**Expected recovery**: prevents the next ~20 doomed records from running. Doesn't recover the
already-failed ones — combine with Fix #4 (server re-raise) to surface auth issues immediately.

**Risk to Layer A**: false positive only if 3 consecutive healthy records legitimately produce
empty final_answer + 0 tokens — Mode A preflight rules this out.

### Fix #4 — Server-side re-raise on agent-loop crash

**File**: `agent/run_agent_v2.py:459-463` (already proposed in
`v4_cons_fail_root_cause.md:90-104`, not yet applied):

```python
        except Exception as e:
            print(f"[Error] Agent loop failed: {e}")
            traceback.print_exc()
            self.trace_collector.finish_session(success=False, error=str(e))
            raise   # ← surface to api/server.py:194, returns HTTP 500 with detail
```

Plus in `agent/api/server.py:194-202`, branch on `AuthenticationError` to return 503 with auth-
specific detail; keep generic 500 otherwise.

**Risk to Layer A**: medium. Changes external behaviour for other callers of the agent server. Audit
baselines (B5_Direct, B7_SelfRefine, B1-B4) for empty-string handling before deploying. Probably
safe — those baselines don't call this server.

### Fix #5 — Diagnose the Mode I trigger by removing the silent `ValueError` catch

**File**: `agent/api/server.py:191-192`. Temporarily change to:
```python
    except ValueError as e:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=400, detail=str(e))
```

So the agent server log captures the Pydantic detail when the next Mode I record fires. After
diagnosis, decide between (a) fixing the trace to satisfy `RunResponseV2`, or (b) hardening
`_build_response` to never produce an invalid response object.

**Risk to Layer A**: zero — pure logging. Roll back after diagnosis.

### Fix #6 — Clarify `_VIZ_TYPE_USE_CASES` to disambiguate 2-curve plots

**File**: `code/agent_tools/generate_viz.py:85-96`.

```python
    "chartjs_line": (
        "trend over an ordered axis (time, sequence, or x-coordinate); "
        "use for 1+ continuous curves vs a shared x-axis — NOT just for time-series. "
        "A two-line plot of f(x) and g(x) on the same axes IS chartjs_line."
    ),
    ...
    "mermaid_flowchart": (
        "discrete named-entity relationships, processes, or dependencies. "
        "NOT for plots of continuous functions — use chartjs_line / chartjs_scatter instead."
    ),
```

**Expected recovery**: +1 (qid 05). Across the bulk, +3-5 records where the source is a clean
2-curve plot but the model picked flowchart.

**Risk to Layer A**: minor. The macro TMG rule-routing in `tmg.py:31-37` still hard-routes
relational queries to flowchart; this only refines the in-tool choice.

### Fix #7 — Drop fabricated `mermaid_flowchart` fallback in mapper

**File**: `code/adapters/viz_output_mapper.py:265-268`.

```python
    if not viz_type:
        viz_type = ""    # was: viz_type = fallback_viz_type
        viz_dsl = response.final_answer
```

Already proposed in `v4_cons_fail_root_cause.md:121-135`. Pure analysis hygiene — removes the
"100 % of failures look like mermaid_flowchart" artifact.

**Risk to Layer A**: zero.

### Fix #8 — Strip mermaid styling directives before sidecar write

**File**: `code/agent_tools/generate_viz.py` (after parsing `viz_dsl` in `execute()`,
~line 320).

```python
if out_viz_type.startswith("mermaid_") and viz_dsl:
    import re as _re
    viz_dsl = "\n".join(
        line for line in viz_dsl.splitlines()
        if not _re.match(r"^\s*style\s+\S+\s+fill:", line)
        and not _re.match(r"^\s*classDef\s+", line)
    )
    # Squash <br/> inside (( )) node labels — renderer chokes on them.
    viz_dsl = _re.sub(r"(\(\([^)]*?)<br/>([^)]*?\)\))", r"\1 \2", viz_dsl)
```

**Expected recovery**: +2 of 24 (qid 01, 05 syntax_valid → render_success). Across the bulk, likely
+3-5.

**Risk to Layer A**: minor. Strips styling lines that carry no semantic content. The 16 healthy
Layer-A B6 records that DO render don't use these directives (verified by inspecting
`outputs/prototype/viz/all.json`).

---

## Section 4 — Fundamental limit vs fixable

| Class | Records (n=24) | Notes |
|---|---|---|
| FIXABLE — infrastructure | Mode I (3) + Mode A1 (~10) + Mode A2 (~5) + Mode C (3) ≈ 21 of 24 | Fixes #1-#5; bulk recovery via #1+#2 in the near term |
| FIXABLE — method | Mode R (2 of 3 sv=True) + Mode T' (1) ≈ 3 of 24 | Fixes #6 + #8 |
| FUNDAMENTAL LIMIT | Mode T ≈ ≥10 records across the full 50-record bulk (qids 00, 01, 02, 06, 08, 09, 11, 14, 16, ...) | Source figure has multi-panel / treemap / box-plot composition that none of the 10 subtypes can express |
| Already successful | 1 rendered (qid 04) + 2 syntax-valid (qid 01, 05) | — |

**Best-case projection** (Fixes #1-#8 applied):

- Mode I recovered: +3 (qids 00, 02, 03) → 4 successful within qids 00-04 ≈ 80 % of feasible
  subset.
- Mode A1/A2 recovered (once auth is rotated + retry broadened): ~12 of ~15 records.
- Mode R recovered: +2 (qids 01, 05 render success).
- Total projected: ~18 of 24 = **75 %**. Remaining ~6 are Mode T fundamental.

The 5-record preflight (B6 exec_rate 0.2 vs B1 1.0, B5_Direct 1.0, B7_SelfRefine 0.8) is consistent:
qids 00-04 are dominated by Mode I + Mode R, both fully fixable. **Mode T doesn't appear in
qids 00-04**, so the gap on that small window is 100 % fixable.

On the full 50-record Plot2Code bulk, the realistic ceiling is **70-75 % vs B1's 100 %**
(Δ ≈ -25 to -30 pp). That ceiling is taxonomy-bound and is the honest gap to report. Going further
requires either expanding the 10-enum (paper-design change) or admitting Plot2Code as a partial
out-of-scope source.

---

## Section 5 — Cross-cutting observations

**5.1 Plot2Code amplifies Mode I 5× vs Layer A.** Layer A had 1/40 Mode-D 400s (2.5 %); Plot2Code
shows 3/24 (12.5 %). The likely driver: **single-doc bundles** (`n_docs == 1` consistently in
Plot2Code). The response-side Pydantic validation in `_build_response`
(`agent/api/handlers.py:255`) appears to fail more often when `inputs_used == 1` and a custom tool
was invoked. The diagnostic patch in Fix #5 will pin this down.

**5.2 Single-doc + descriptive content → no query_type routing.** Plot2Code queries are external/
descriptive ("The figure ... consists of three plots"); `build_tmg_rule("external")` returns ""
(`tmg.py:154-156`), so the agent sees only `V4_POOL_EXPOSURE_RULE` with all 10 subtypes available.
Right behaviour for Plot2Code, but it makes Mode T' more likely without macro narrowing — strengthening
the case for Fix #6 (clearer use-case hints).

**5.3 Mode mapping with the Text2Vis subagent.**
- Their Mode A = our A1 + A2.
- Their Mode B = our B (n_steps_max, no tool call) — **not observed in Plot2Code window** because A1
  prevents the agent from reaching the loop body. Will appear once auth is fixed.
- Their Mode C = our C.
- Their Mode D = our I. Plot2Code amplifies 5×.

**5.4 Sidecar-based output contract is the methodological win.** That the tool's sidecar contains
the right output even when the agent server returns 400 is direct evidence the V4_consolidated
method works; the surrounding pipeline is what's failing. Publishable framing: "agent-loop + tool-
call architecture produces correct viz outputs in cases where the surrounding pipeline silently
masks infrastructure errors — adopting the sidecar-recovery contract (Fix #1) gains ~12 pp on
held-out with no change to prompts or examples."

**5.5 Recommended action sequence.**
1. Apply **Fix #7** (drop mermaid fallback) — zero-risk hygiene.
2. Apply **Fix #2** (broaden retry trigger) — small extension of existing retry.
3. Apply **Fix #5** (diagnostic ValueError logging) — observe next Mode I trigger.
4. **Operator**: rotate vLLM auth token, verify fresh load before re-running.
5. Apply **Fix #1** (sidecar rescue) — write a small unit test simulating 400 + sidecar present,
   then bulk-rerun Plot2Code qids 00, 02, 03 to confirm.
6. Apply **Fix #8** (mermaid styling strip) — concurrent with Fix #1.
7. Apply **Fix #3** (auth batch-halt) — protect future bulk runs.
8. Conditional on (1-7): **Fix #6** (subtype-choice prompt) once infra noise is gone.
9. Then **Fix #4** server re-raise — most invasive, do last, audit baselines first.

---

## Notes on snapshot scope

- 24 of ~45 expected B6 records analyzed. The in-flight bulk is adding records that match the
  Mode A1 signature exactly (auth window persists). If auth is fixed mid-bulk, expect +6-10
  successes (mix of Mode-T-feasible qids) and +2-3 Mode T failures. If auth stays broken, all
  remaining records will be Mode A1.
- The 3 Mode I records (00, 02, 03) and 3 R/successful records (01, 04, 05) are stable findings —
  they ran in the morning preflight window before the auth issue began, so they represent
  "infrastructure-healthy single-doc Plot2Code" outcomes for V4_cons.
- Mode T conclusions (taxonomy ceiling) are content-driven and stable as more records arrive.
