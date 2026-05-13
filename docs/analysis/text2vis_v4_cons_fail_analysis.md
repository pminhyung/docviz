# V4_consolidated Text2Vis Fail-Mode Analysis (2026-05-13)

Held-out gap: V4_cons 82% syntax_pass on Text2Vis vs S1_Direct 97 / B3_CoDA 96 / B4_ViviDoc 94 / B2_NVAGENT 92 — a 10–15 pp deficit driven entirely by 18 failures distributed across 6 distinct fault modes. **5 of 6 modes are architectural (agent loop / tool-call / brace truncation), not content/schema knowledge gaps.** Only Mode B has a Text2Vis-specific flavor (the single-doc table-with-reference-code bundle confuses the agent into skipping `generate_viz`).

Source data: `outputs/text2vis/viz/raw.jsonl` (filtered by `strategy == "S4_AgenticTMGv4_consolidated"`, n=100). Bundles: `data/prototype/bundles/text2vis.json`. Tool sidecar artifacts: `/tmp/v4_viz_outputs/v4_consolidated_text2vis_*.json`.

V4_cons is the ONLY pipeline with `empty_dsl > 0` on Text2Vis (9 records). All 9 baselines and ablations finish with a non-empty viz_dsl string.

## 1. Summary table

| Mode | Count | Records | Root cause | Highest-leverage fix | Δ recoverable | Risk to Layer A |
|---|---|---|---|---|---|---|
| **A** Mode-A silent crash, post-retry | 4 | 095, 096, 097, 099 | Both first call AND round-robin retry hit upstream LLM ConnectError → 200 OK with empty `final_answer`, tok=0, dur≈6.7 s | Add per-host bad-host cooldown + 2nd retry (3 total) before giving up; honor `tokens_out>0` as success even with empty final_answer when sidecar exists | +3-4 pp | none — pure infra resilience |
| **B** Agent ran but did not invoke `generate_viz` | 6 | 005, 012, 043, 060, 064, 094 | Single-doc bundle + small content (~600 chars) makes agent treat one `ReadFullDocument` as sufficient, then it emits `<final_answer>` with prose/JSON ack directly — `generate_viz` skipped despite V4_POOL_EXPOSURE_RULE | **Surface the agent's missing-tool-call as a server-side hard reject** OR add a fallback in the orchestrator: when sidecar missing AND final_answer contains a DSL block, re-route through `_extract_dsl_block` (works for 0–3 of 6); preferred long-term: rewrite the V4 rule into a server-enforced precondition in `agent/core/output_validator.py` | +5-6 pp | low — same rule, same enforcement on Layer A (which has the same Mode-B failures) |
| **C** 600 s client timeout | 0 | — | none observed on Text2Vis | n/a | 0 | n/a |
| **D** Sidecar written, agent envelope HTTP-400 reject | 2 | 002, 055 | Tool ran successfully (sidecar exists at `/tmp/v4_viz_outputs/v4_consolidated_text2vis_002_text2vis.json` and `_055_…json`, both parse-clean), but the subsequent agent response was 400-rejected. Orchestrator never reads the sidecar because `HTTPStatusError` propagates through `s4_agentic_tmg.py:run` to `run_prototype.py:168` which discards everything | **Catch `HTTPStatusError` inside `s4_agentic_tmg.py:run` after `_do_run` and try the sidecar before re-raising** | +2 pp | none — sidecar fallback is V4-only |
| **G** chartjs DSL parse_fail: missing one closing brace | 5 | 020, 026, 045, 057, 090 | `generate_viz` inner LLM call hits `max_tokens=4096` inside JSON-grammar-constrained sampling. vLLM's structured-output grammar closes the OUTER `}` (the `{"viz_type": ..., "viz_dsl": "<STRING>"}` envelope) but the INNER DSL string content gets one `}` short. Empirically: `dsl + "}"` parses cleanly on all 5. Strong correlation with the `annotation` plugin (4/5 fails include it; the plugin adds 3 extra brace levels) | (a) Lower exemplar complexity / strip `annotation` from prompt; (b) **Add a "balance-and-retry" auto-repair pass in `generate_viz.py:299-318`**: when inner DSL has unbalanced braces, append the missing `}` and re-parse; (c) raise `max_tokens` from 4096 → 6144 for the tool LLM call | +5 pp | none — Layer A has the same pattern (11/12 chartjs parse_fails there are also missing-1-brace) |
| **H** chartjs DSL parse_fail: invalid `\'` escape | 1 | 025 | Model wrote `Pearson\\'s` (an invalid JSON escape) inside a `title.text` string | Reuse the same auto-repair: replace `\\'` with `'` (or `\\u2019`) before parse. Already covered by the balance-and-repair pass if it also normalizes invalid escapes | +1 pp | none |

Total recoverable: ~14-16 pp out of the 18 fails. After fixes V4_cons should land at ~96-98 % syntax_pass — at parity with S1_Direct and ahead of B2_NVAGENT.

## 2. Per-mode detail

### Mode A — silent infra crash, post-retry (4 records)

These are the classic Mode-A pattern documented in `docs/analysis/v4_cons_fail_root_cause.md` §"Mode A — the dominant failure path", but with the retry in `s4_agentic_tmg.py:236-243` ALREADY firing once and ALSO hitting the same silent crash on a different host.

| record_id | dur (s) | tok_out | sub_q | errors |
|---|---|---|---|---|
| `text2vis_095_text2vis` | 6.770 | 0 | 0 | `agent returned empty final_answer` + sidecar missing |
| `text2vis_096_text2vis` | 6.865 | 0 | 0 | same |
| `text2vis_097_text2vis` | 6.699 | 0 | 0 | same |
| `text2vis_099_text2vis` | 6.818 | 0 | 0 | same |

The 6.7 s duration is dur(call1) + 3 s sleep + dur(call2). Each underlying call is ~1.8-2 s of failing fast against a wedged vLLM host. The retry block at `code/pipelines/s4_agentic_tmg.py:236-243` picks a new host via `_next_reasoner_url()`, but at 100-record scale 4/100 = 4 % of records still land on a bad host TWICE (the 9-host cluster's bad-host overlap is enough to make this likely under round-robin without bad-host quarantine).

The 4 affected records are consecutive in query_id (095-099, with 098 succeeding). This is consistent with a single-host outage window of ~30-60 s. `text2vis_099` is the last record in the set, so a tail-end host wedge explains the streak.

### Mode B — agent skipped `generate_viz` (6 records)

| record_id | viz_type | dur (s) | tok_out | sub_q | final_answer body |
|---|---|---|---|---|---|
| `text2vis_005_text2vis` | `mermaid_flowchart` | 120.3 | 4408 | 0 | empty |
| `text2vis_012_text2vis` | `mermaid_flowchart` | 86.9 | 3620 | 0 | empty |
| `text2vis_043_text2vis` | `mermaid_flowchart` | 151.0 | 13409 | 0 | prose summary (200-char excerpt below) |
| `text2vis_060_text2vis` | `mermaid_flowchart` | 154.0 | 13312 | 0 | prose summary |
| `text2vis_064_text2vis` | `mermaid_flowchart` | 147.7 | 13349 | 0 | prose summary |
| `text2vis_094_text2vis` | `mermaid_flowchart` | 140.8 | 12599 | 0 | empty |

Excerpt from `text2vis_043_text2vis.viz_dsl` (the prose final_answer that viz_output_mapper retained because `_extract_dsl_block` returned `("", text)`):

```
text2vis_043_01_text2vis-table-43.json covers a data table featuring entities
such as Other, Northern League, and Five Star. It includes discussions on
calculating the proportion of 'Strongly' responses across entities and
identifying significant deviations. The document addresses issues related to…
```

This is the agent's summary of the input doc, NOT a viz. `viz_output_mapper.py:265-268` then falls back to `viz_type = "mermaid_flowchart"` (line 262 default), which is the only reason these records carry that label. The agent's real viz_type was **never decided** — it skipped step (2) `<tool_invoke>generate_viz` entirely and jumped to step (3) `<final_answer>`.

`sub_queries=0` for all 6: the agent didn't even hit `search` or `ReadFullDocument` (single-doc bundle + reference summary inline → agent assumes step-1 doc snippet is sufficient and goes straight to final_answer).

Why Text2Vis is hit harder than Layer A: the bundle's `docs[0].content` (~600 chars on average, max 1142) is so short that the doc-step prompt's preview captures the entire CSV table + reference summary. The agent then has no need to retrieve anything, gets confused about what step it's on, and produces final_answer without invoking the tool. Layer A's multi-doc bundles (`hotpot_*` with 5-10 docs, `10k_*` with 50+ pages) force at least one retrieval, which keeps the rule-17/18 sequence intact.

### Mode D — sidecar-written, envelope-rejected (2 records)

| record_id | viz_type | dur (s) | tok_out | errors |
|---|---|---|---|---|
| `text2vis_002_text2vis` | `''` | 128.1 | 0 | `HTTPStatusError: 400 Bad Request for 'http://localhost:9037/v2/run'` |
| `text2vis_055_text2vis` | `''` | 140.7 | 0 | same |

The sidecars are present on disk (`stat /tmp/v4_viz_outputs/v4_consolidated_text2vis_002_text2vis.json` → 2026-05-13 08:53:39; `_055_…` → 10:33:34). Both parse as valid Chart.js JSON:

- `text2vis_002`: chartjs_line, 920 chars, 13 `{` = 13 `}`, parses cleanly, ends `…"plugins":{"title":{"display":true,"text":"Net Sales 2013-2020: Actual vs Forecast (11.96% CAGR) — 2020 Variance: 1002.78 Million USD"},"legend":{…}}}}`.
- `text2vis_055`: chartjs_bar, 790 chars, 12 = 12, parses cleanly.

So the tool ran end-to-end successfully (LLM responded, JSON parsed, sidecar written). The HTTP-400 then came from the agent's *outer* envelope. Path:

1. `code/adapters/agent_client.py:290` — `resp.raise_for_status()` raises `httpx.HTTPStatusError`.
2. `code/pipelines/s4_agentic_tmg.py:206-224` — `_do_run` does not catch; raises to caller.
3. `code/run_prototype.py:168` — outermost catch builds a degraded VizOutput with `viz_type=""` and `errors=[HTTPStatusError…]`. Sidecar is never read. The viz is silently discarded.

The orchestrator's `_read_viz_sidecar` (s4_agentic_tmg.py:50-73) sits AFTER `_do_run` returns, so it's unreachable on the 400 path.

Probable origin of the 400 itself: `agent/api/handlers.py:91-96` raises `ValueError` if `reasoner_api_key` is missing AND `X-Admin-Secret` is not verified, which becomes 400 at `agent/api/server.py:192`. The likely trigger is a Pydantic validation race when the retry path passes a different `reasoner_base_url` whose model_router config flipped — but the root cause is incidental; what matters is the orchestrator throws away the already-written sidecar.

### Mode G — chartjs missing-one-closing-brace (5 records)

| record_id | viz_type | len(dsl) | `{` | `}` | `dsl + "}"` parses? | `annotation` present? |
|---|---|---|---|---|---|---|
| `text2vis_020` | chartjs_line | 1169 | 17 | 16 | yes | yes |
| `text2vis_026` | chartjs_bar | 771 | 15 | 14 | yes | yes |
| `text2vis_045` | chartjs_line | 989 | 16 | 15 | yes | yes |
| `text2vis_057` | chartjs_line | 1365 | 17 | 16 | yes | yes |
| `text2vis_090` | chartjs_bar | 1067 | 16 | 15 | yes | yes |

Tail of `text2vis_020_text2vis.viz_dsl` (last 200 chars):

```
…"annotation":{"annotations":{"zeroCrossing":{"type":"point","xValue":4,
"yValue":0.37,"backgroundColor":"rgb(75, 192, 192)","radius":6,"label":
{"display":true,"content":"Prediction: Trend reaches zero at ~32 months",
"position":"top"}}}}}}
```

Six trailing `}` — should be seven. The `annotation.annotations.zeroCrossing.label` nesting drives 3 extra brace levels beyond what the consolidated exemplar uses (the exemplar has 0 `annotation` references; see `code/agent_tools/oneshot_pool.json` `consolidated.chartjs_line` content — `"annotation"` substring is absent).

**Root cause** at `code/agent_tools/generate_viz.py:251-268`:

```python
return client.chat.completions.create(
    model=self._model,
    messages=[{"role": "user", "content": prompt}],
    temperature=0.7,
    top_p=0.8,
    seed=42,
    max_tokens=4096,
    response_format={"type": "json_object"},
    extra_body={"top_k": 20, "min_p": 0, "chat_template_kwargs": {"enable_thinking": False}},
)
```

vLLM's `response_format={"type": "json_object"}` enables grammar-constrained JSON sampling. When the model approaches `max_tokens=4096`, the grammar forces it to close the outer JSON object (the envelope `{"viz_type": "...", "viz_dsl": "<STRING>"}`). To do that, it must finish the inner `viz_dsl` string with `"` and then write `}`. The "finish the inner string" stop is rule-driven: the grammar accepts any character inside the string, so it just terminates the string when forced — often one `}` short of being valid JSON content within that string. The outer envelope is valid JSON; the *inner string content* is one `}` short of valid JSON.

This is also visible in Layer A: 11 of 12 chartjs parse_fails there are the same pattern (`dsl + "}"` parses cleanly). Cross-cutting bug, not Text2Vis-specific.

Correlation with `annotation` plugin in the inner DSL: 5/5 of the missing-brace fails contain `annotation`. The prompt at `code/agent_tools/generate_viz.py:397-407` explicitly warns against adding plugins not in the exemplar, but Qwen3.5-397B-FP8 still adds `annotation` in 8 records (3 succeed, 5 fail; 62.5 % failure rate when `annotation` is present vs 14 % overall).

### Mode H — invalid `\'` escape (1 record)

| record_id | viz_type | len(dsl) | parse error |
|---|---|---|---|
| `text2vis_025_text2vis` | chartjs_bar | 1049 | `Invalid \escape: line 1 column 957 (char 956)` |

The offending substring at chars 940-975:

```
…"ve Skew (Pearson\\'s 2nd Coeff 0.87)"…
```

`Pearson\\'s` is a JSON-syntactically-invalid escape. The model wanted to write `Pearson's`, but during the round-trip from outer envelope (`"viz_dsl": "...\"...Pearson's..."`) it inserted `\\'` to escape the apostrophe. JSON does not recognize `\\'` as a valid escape; only `\\u0027`, `\\\"`, `\\\\` or the literal `'` would be valid. Same root: the model is reasoning about double-nested string-escape correctness and getting one level wrong.

A trivial repair regex would fix this: `re.sub(r"\\\\\\'", "'", dsl)` (or normalize all unrecognized escapes).

## 3. Prioritized fix proposals

Fixes ordered by leverage × low-risk.

### Fix #1 (highest leverage, +5 pp, Layer-A safe) — auto-repair pass in `generate_viz.py`

After parsing the OUTER envelope at `code/agent_tools/generate_viz.py:303-318`, before writing the sidecar, run a brace-balance + escape-repair check on the extracted `viz_dsl`. If `viz_dsl` is supposed to be Chart.js JSON (`viz_type` starts with `chartjs_`), try `json.loads(viz_dsl)`; on failure try (i) append `}` × {1,2}, (ii) strip invalid `\\'` escapes, (iii) replace unrecognized backslash sequences with their literal character. Persist whichever variant parses.

**Location**: `code/agent_tools/generate_viz.py:320` (right after the `if not viz_dsl: return error_status` line, before `sidecar_path.write_text`).

**Diff sketch**:

```python
# Auto-repair pass for chartjs DSL — handles the two recurring tool-output
# bugs: (a) missing one closing brace due to JSON-grammar-constrained
# truncation at max_tokens; (b) invalid '\\'' escape sequences.
if out_viz_type.startswith("chartjs_"):
    try:
        json.loads(viz_dsl)
    except json.JSONDecodeError:
        repaired = viz_dsl.replace("\\\\'", "'")  # Mode H
        for n_extra in (1, 2, 3):
            try:
                json.loads(repaired + ("}" * n_extra))
                viz_dsl = repaired + ("}" * n_extra)
                break
            except json.JSONDecodeError:
                continue
```

Expected recovery: 6 of 6 Mode G + Mode H records (the brace counts and `\\'` substring confirm trivial repair). Risk to Layer A: none — same auto-repair would recover 11 of 12 Layer A chartjs parse_fails (cross-checked). All-modes only ADDS valid records; never invalidates one.

### Fix #2 (high leverage, +2 pp, Layer-A safe) — read sidecar before re-raising HTTP error

`code/pipelines/s4_agentic_tmg.py:206-264` — wrap `_do_run` in try/except. On `HTTPStatusError`, before re-raising, attempt to read the sidecar (already written by the tool on the FIRST successful tool call). If found, build a `VizOutput` from sidecar + the HTTP error as a warning.

**Location**: `code/pipelines/s4_agentic_tmg.py:224` (the line `response = _do_run(self._reasoner_base_url)` and the retry at 243).

**Diff sketch**:

```python
import httpx
try:
    response = _do_run(self._reasoner_base_url)
except httpx.HTTPStatusError as e:
    # Tool may have already written the sidecar before the envelope reject.
    if self.mode in ("v4_pool", "v4_consolidated"):
        sidecar = _read_viz_sidecar(self.mode, query_id)
        if sidecar and sidecar.get("viz_dsl"):
            return VizOutput(
                viz_dsl=sidecar["viz_dsl"],
                viz_type=sidecar.get("viz_type", ""),
                rendered_image_path="",
                render_success=False,
                retrieved_chunks=[],
                sub_queries=[],
                source_attribution={},
                tokens_in=0,
                tokens_out=0,
                cost_usd=0.0,
                errors=[f"agent envelope HTTPStatusError but sidecar recovered: {e}"],
            )
    raise
```

Expected recovery: 2 of 2 (records 002, 055 both have parseable sidecars on disk right now). Risk to Layer A: none — sidecar fallback only triggers when sidecar exists, which means the tool ran successfully. Cannot mask a real content failure.

### Fix #3 (high leverage, +3-4 pp, Layer-A safe) — second retry with bad-host quarantine

`code/pipelines/s4_agentic_tmg.py:236-243` — current logic retries ONCE on a round-robin host. Extend to retry up to 2 more times, quarantining each failed host for 60 s in a module-level `_BAD_HOSTS_UNTIL: Dict[str, float]` map. `_next_reasoner_url()` skips hosts whose quarantine has not expired.

**Location**: `code/pipelines/s4_agentic_tmg.py:91-105` (add `_BAD_HOSTS_UNTIL`) and `_next_reasoner_url` extended with quarantine check, then `code/pipelines/s4_agentic_tmg.py:236-243` extended to 2 retries with quarantine update.

**Diff sketch** (sketch only, full impl would also need lock semantics):

```python
_BAD_HOSTS_UNTIL: Dict[str, float] = {}
_BAD_HOST_COOLDOWN_S = 60.0

def _next_reasoner_url() -> str:
    # ... existing round-robin pick ...
    # skip hosts currently quarantined
    now = time.time()
    for _ in range(len(hosts)):
        candidate = hosts[idx % len(hosts)]
        if _BAD_HOSTS_UNTIL.get(candidate, 0.0) <= now:
            return f"http://{candidate}/v1"
        idx += 1
    return f"http://{hosts[0]}/v1"  # all quarantined → fall back to first
```

And in `run()`:

```python
for attempt in range(3):  # 1 initial + 2 retries
    response = _do_run(url)
    if not (not response.final_answer and response.total_tokens == 0
            and response.total_duration_seconds < 5.0):
        break  # success-or-real-failure
    # Mode A pattern — quarantine the host and retry
    _BAD_HOSTS_UNTIL[host_of(url)] = time.time() + _BAD_HOST_COOLDOWN_S
    time.sleep(3.0)
    url = _next_reasoner_url()
```

Expected recovery: 3-4 of 4 Mode A records. Risk to Layer A: low — same fix would help Layer A's 26 Mode-A records (per `v4_cons_fail_root_cause.md`). Quarantine map is process-local and bounded.

### Fix #4 (medium leverage, +5-6 pp, Layer-A safe) — server-side rule-17/18 enforcement

For Mode B: the V4_POOL_EXPOSURE_RULE is a prompt-level instruction. Qwen3.5-FP8 violates it ~6 % of the time on single-doc Text2Vis. Convert to a server-side hard precondition: in `agent/core/output_validator.py` (or via `RunRequestV2.constraints.required_tools=["generate_viz"]` if the validator already supports it — line 37 shows the `required_tools` field already exists), refuse the run with a clear error if `generate_viz` was not invoked before `<final_answer>` when `custom_tools_path` is set AND `tool_secrets.tmg_mode` is one of `v4_*`.

**Location**: `code/adapters/agent_client.py:243-275` (`_post_run` body construction — pass `constraints={"required_tools": ["generate_viz"]}` when V4 mode is active) AND `agent/core/output_validator.py:364`-style enforcement to make it a fail-stop, not a warning.

**Risk to Layer A**: the SAME 6 % rule-skip pathology occurs there (Mode B in `v4_cons_fail_root_cause.md` is 10/40 = 25 % of Layer A fails). Server-side enforcement would convert those silent skips into explicit errors, which the orchestrator can then handle (e.g., retry once with a stronger system prompt prefix). Net effect on Layer A: probably positive once paired with a retry.

A simpler interim fix at the orchestrator level: when sidecar is missing AND `_extract_dsl_block(final_answer)` returns a valid (viz_type, viz_dsl) tuple, accept that — Mode B records 005 and 094 have empty final_answer (no fallback possible) but the others have prose that COULD contain a fenceless DSL in some cases. Inspection shows none of the 6 had a parseable DSL in final_answer, so this interim fix yields 0 additional recoveries on Text2Vis; the server-side enforcement is the only path that pays off here.

### Fix #5 (low leverage, +1-2 pp, low risk) — raise tool LLM `max_tokens` and remove `annotation`-permitting language

Increasing `max_tokens` from 4096 to 6144 in `code/agent_tools/generate_viz.py:261` would reduce the brace-truncation rate at the source, before the auto-repair (Fix #1) even runs. Combined with explicitly listing `annotation`, `tooltip.callbacks`, `ticks.callback` as FORBIDDEN keys (the current prompt at `generate_viz.py:400-407` says "do NOT add tooltip callbacks…" but uses a "significantly increase the risk" tone that the model treats as a strong-suggestion-not-hard-rule), the inner DSL stays simpler and well within 4096 tokens.

**Location**: `code/agent_tools/generate_viz.py:261` (raise max_tokens) and `generate_viz.py:397-410` (replace soft "do NOT add … significantly increase the risk" with hard "FORBIDDEN. Including any of these keys causes the run to be discarded: `annotation`, `tooltip.callbacks`, `ticks.callback`, `scales.*.callback`, `animation`, `plugins.datalabels`. Use only `data`, `options.responsive`, `options.scales`, `options.plugins.title`, `options.plugins.legend`.").

**Risk to Layer A**: minimal — Layer A's good chartjs records (e.g., temporal hotpot) rarely use these advanced plugins anyway; removing them costs no information. Prompt-only change.

## 4. Cross-cutting observations

- **Text2Vis is NOT a new failure mode**, it amplifies existing modes. Mode G (missing-1-brace) exists in Layer A at 11/12 chartjs parse_fails (Mode A `v4_cons_fail_root_cause.md` doesn't break this out — it's bundled under "syntax_fail"). Mode B (skip-generate_viz) is 25 % of Layer A fails. Modes A and D are infrastructure modes shared by all V4 runs.

- **The "schema/format mismatch" framing in the task brief is partially wrong**. The agent IS schema-aware on Text2Vis — 100 % of successful records picked chartjs (none picked mermaid), correctly matching tabular input to chart output. The 10 "mermaid_flowchart" records in the failure set are all `viz_output_mapper.py:262` fallback labels on records where the agent never picked a viz_type at all (sidecar missing). Real viz_type distribution on Text2Vis fails: `chartjs_bar=3, chartjs_line=3, chartjs_scatter=0, NONE=12`. There is no evidence the agent picks the wrong chartjs subtype on Text2Vis content.

- **The `annotation` plugin is the single biggest content-level trigger**. 8 records used it; 5 failed (62.5 %). Among the 92 records without `annotation`, 79 succeed (86 %). Prompt-level prohibition + auto-repair would address most of the failure tail without touching the agent.

- **Plot2Code is unaffected**. `outputs/plot2code/viz/raw.jsonl` shows 0 chartjs parse_fails for B6, because Plot2Code is too small (19 records) and its DSLs are simpler. Mode B / Mode A are still infrastructure issues that affect Plot2Code IF run at higher scale.

- **Single-doc bundle is the Text2Vis-specific stress on Mode B**. The single-doc + ~600-char content lets the agent's step-1 doc summary "feel" complete, removing the natural cue (multi-doc retrieval) that triggers the rule-17/18 sequence in Layer A. Workaround inside `code/adapters/bundle_to_docai.py` would be to inject a synthetic second doc with the rule reminder, but Fix #4's server-side enforcement is cleaner.

## 5. Recommended order of operations

1. **Fix #1** (auto-repair pass in `generate_viz.py`) — single-file change, +5-6 pp, zero Layer-A risk, ships in ~10 min.
2. **Fix #2** (read sidecar before re-raising HTTP error in `s4_agentic_tmg.py`) — single-file change, +2 pp, zero Layer-A risk.
3. **Fix #5** (raise `max_tokens` + forbid plugins in tool prompt) — single-file change, +1-2 pp marginal on top of Fix #1, reduces the load on the auto-repair path.
4. **Fix #3** (bad-host quarantine + 2-retry) — single-file change, +3-4 pp, zero Layer-A risk. Helps Layer A more than Layer B.
5. **Fix #4** (server-side rule-17/18 enforcement) — two-file change (validator + client constraints), +5-6 pp, requires preflight on a small Layer A subset to confirm enforcement doesn't reject borderline-good records.

After Fix #1 + Fix #2 + Fix #5 alone, V4_cons should clear ~92-94 % on Text2Vis (at parity with B2/B4) without touching any Layer A behavior. Adding Fix #3 and Fix #4 pushes to ~96-98 %.
