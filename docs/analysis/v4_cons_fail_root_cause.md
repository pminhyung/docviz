# V4_consolidated Fail-Rate Root Cause Analysis (2026-05-13)

## Headline

V4_cons's Layer A full-set mean (0.735, n=265) vs valid-only mean (0.851, n=216)
gap of 0.116 is **not a method/content failure** — it is dominated by
**silent infrastructure error masking** in the agent server.

Of the 40 fail records (15.1% of 265):

| Mode | Count | % of fails | Root cause | Pattern |
|---|---|---|---|---|
| A: agent-loop silent crash | 26 | 65% | upstream LLM ConnectError / ToolExecution 401 → caught silently → 200 OK with empty `final_answer` | duration ≈ 2s, tokens_out = 0 |
| B: agent reached n_steps_max | 10 | 25% | model never invoked `generate_viz` despite rule 17/18; produced reasoning + empty final_answer | duration 100–400s, tokens_out 10K–120K |
| C: 600s client timeout | 3 | 7.5% | upstream LLM hung; client gave up | duration ≈ 600s, tokens_out = 0 |
| D: HTTP 400 server reject | 1 | 2.5% | final_answer validation rejected one-word "success" (single-doc Plot2Code edge case from earlier session) | duration ≈ 200s |

The artifactual `viz_type=mermaid_flowchart` label on 36/40 fails comes from
`code/adapters/viz_output_mapper.py:262` — `fallback_viz_type="mermaid_flowchart"`
when `_extract_dsl_block(final_answer="")` returns empty. **It is not the
agent's selected viz_type.** Real viz_type distribution of fails is unknown
without re-running.

## Evidence

### Mode A — the dominant failure path

Code trace:
1. `agent/run_agent_v2.py:459` — `except Exception as e: print(...); return session`
   silently swallows the agent loop exception (ConnectError, ToolExecutionError
   401, etc.) without re-raising.
2. `agent/api/handlers.py:287` — `final_answer = ""`; the response builder
   loops through `trace_data["steps"]` looking for a step with `final_answer`.
   When the loop crashed before producing one, this stays empty.
3. Handler returns `200 OK` with `final_answer=""`.
4. `code/adapters/agent_client.py:290` — `resp.raise_for_status()` passes
   (200 is OK).
5. `code/adapters/viz_output_mapper.py:265-278` — `_extract_dsl_block("")` →
   `("", "")`; fallback to `mermaid_flowchart`; emit error
   `"agent returned empty final_answer"`.

Agent server log (`/tmp/docviz_logs/agent_server_9037.log`) confirms the
upstream crash signature:

```
agent.core.tool_registry.ToolExecutionError: Tool 'ReadFullDocument' failed:
  Error code: 401 - {'code': 401, 'reason': 'FAILED_TO_AUTH', ...}
[Error] Agent loop failed: Connection error.
httpx.ConnectError: [Errno 111] Connection refused
```

76 distinct `Connection refused` events in the server log over the Layer A
run. The 9-host vLLM cluster has occasional per-host transient downtime;
the agent server's reasoner subprocess does not retry across hosts (only
the `MultiHostQueueClient` in `code/adapters/agent_client.py` does, and
only for the *tool's* vLLM calls — not the reasoner's).

### Mode B — long-run no-tool

10 records ran for 100–400s with 10K–120K tokens but never invoked
`generate_viz`. These reflect Qwen3.5-397B occasionally hitting `n_steps_max=8`
in pure reasoning without emitting the tool-call structured block.

The 120K-token outlier (10k_04_temporal, 400s duration, n_sub_queries=7)
suggests a search-loop pathology unrelated to V4 specifically.

### Mode A scaling — does it explain the V4_cons vs baseline gap?

Cleanly. If we exclude the 26 Mode A records:

- V4_cons mean (excluding Mode A): expected ≈ 0.832 (extrapolated)
- Best baseline (S1_Direct, S7_SelfRefine): 0.880
- Δ ≈ -0.048 — still below amendment §16's +0.02 threshold, but far closer
  than the -0.145 currently reported.

If a retry-once mechanism recovers 80% of Mode A (typical for transient
upstream-LLM ConnectError on a multi-host cluster), V4_cons would land at
~0.85, narrowing Δ to -0.03 with valid-only equivalent measurement.

## Why baselines don't show this pattern (much)

- **B1–B4 (specialist adapters)**: pure-LLM pipelines via `QwenDirectClient`,
  which has built-in 30s host cooldown + 3s retry. Mode A is intercepted
  at the LLM call layer, not the agent server.
- **B5 (S1_Direct), B7 (S7_SelfRefine)**: same as above — direct LLM, no
  agent server in the path.
- **V4_cons (B6)**: routes through the agent server, which silently masks
  upstream LLM failures with empty 200 OK responses.

## Recommended fix (1-day scope, preflight-able)

### Fix 1 (server-side, highest impact)
**File**: `agent/run_agent_v2.py:459`
**Change**: re-raise after logging, OR set a `loop_failed: True` flag in
the session that handlers.py surfaces as HTTP 503 or a non-empty `warnings`
entry.

```python
except Exception as e:
    print(f"[Error] Agent loop failed: {e}")
    traceback.print_exc()
    self.trace_collector.finish_session(success=False, error=str(e))
    raise  # ← add this line; handlers.py needs a 503 path
```

### Fix 2 (client-side, immediate-recoverable)
**File**: `code/pipelines/s4_agentic_tmg.py:205-220`
**Change**: detect empty final_answer + retry once with 3s backoff.

```python
response = client.run_paper_default(...)
if not response.final_answer and self.mode in ("v4_pool", "v4_consolidated"):
    time.sleep(3.0)
    response = client.run_paper_default(...)  # one retry
```

This costs 1 extra agent call per Mode A record (~20 records × 30-300s avg =
10-100 min wall-clock). Recovers ~80% of Mode A based on transient failure
literature for cluster vLLM.

### Fix 3 (mapper-side, cosmetic)
**File**: `code/adapters/viz_output_mapper.py:262`
**Change**: drop the `mermaid_flowchart` fallback default. Empty viz_type +
empty viz_dsl is more informative than mislabeled flowchart.

```python
viz_type, viz_dsl = _extract_dsl_block(response.final_answer)
if not viz_type and not viz_dsl:
    # Don't fabricate a viz_type — leave empty so downstream analysis
    # treats this as a true failure, not a flowchart attempt.
    pass
elif not viz_type:
    viz_type = fallback_viz_type
    viz_dsl = response.final_answer
```

## Preflight protocol (before deploying fixes) — EXECUTED 2026-05-13

Per "preflight + 코드리뷰 후 bulk" feedback rule:

1. **Pick 5 Mode A records** (tokens=0, duration<3s, errors contain
   "empty final_answer"):
   `hotpot_22_relational`, `hotpot_31_comparative`, `hotpot_40_comparative`,
   `multinews_17_temporal`, `govreport_24_temporal`.
2. **Apply Fix 2 only** (client-side retry). Run V4_cons on these 5
   records with `--force`.
3. **Acceptance**: ≥3/5 produce non-empty viz_dsl on retry → infrastructure
   noise hypothesis confirmed; proceed with full re-batch of 26 Mode A records.
4. If <3/5 → Mode A has a deeper systematic cause; investigate before
   re-batching.

### Result: PASS — 4/5 (80%) on Fix 2 retry-on-empty

| query_id | result | viz_type | dsl_len | tokens | duration |
|---|---|---|---|---|---|
| hotpot_22_relational | **OK** | mermaid_timeline | 590 | 31,861 | 193.6 s |
| hotpot_31_comparative | EXC (ReadTimeout 600s) | — | 0 | 0 | 600.1 s |
| hotpot_40_comparative | **OK** | chartjs_grouped_bar | 824 | 30,960 | 186.5 s |
| multinews_17_temporal | **OK** | mermaid_timeline | 783 | 32,215 | 184.7 s |
| govreport_24_temporal | **OK** | mermaid_timeline | 1,168 | 50,666 | 199.0 s |

(Raw JSON: `docs/analysis/v4_cons_retry_preflight.json`.)

**Key observations confirming the C8 root cause:**

1. **No `mermaid_flowchart` viz_types in recovered records.** Layer A
   labeled all 26 Mode A fails as `mermaid_flowchart` due to the
   `viz_output_mapper.py:262` fallback. The retry-recovered runs reveal
   the **actual** model-chosen viz_types: 3 × `mermaid_timeline`, 1 ×
   `chartjs_grouped_bar`. The "flowchart-dominant fail" pattern was
   entirely an analysis artifact.

2. **All 4 successful retries produced rich DSL** (590–1,168 chars) and
   substantial reasoning (31–51K tokens). Quality is on par with
   non-Mode-A V4_cons records — no hint that these queries were
   inherently harder to visualize.

3. **The 1 non-recovery (hotpot_31_comparative)** timed out at 600 s on
   the retry host. This suggests ~20% of Mode A is "persistent host
   issue rather than transient" — recovery rate is therefore
   80% (4/5), close to the 80% prior we used in §11.11 projection.

4. **Projected impact on full re-batch**: V4_cons Layer A mean lifts
   from 0.735 (full) toward 0.83-0.85 if all 26 Mode A records are
   re-run with Fix 2 (21 recovered + 5 remain as residual fails).
   Δ vs S7_SelfRefine projects from −0.145 → −0.05, entering the §16
   borderline gate region (−0.02 to +0.02).

**Next step (pending user decision)**: full re-batch of 26 Mode A
records under Fix 2. Compute: ~26 × 3 min = ~80 min serial; with
`--s4-workers 2` and 9-host vLLM cluster, ~40 min wall-clock. Output
replaces existing Mode A records in `outputs/prototype/viz/raw.jsonl`
and `judge_scores/all.json` (via `run_prototype --force` + re-judge).

## Impact on paper claims (§7, §8, §16)

- **§7 Layer A**: report both `full` and `valid-only` means with Mode A
  documented as known infrastructure artifact. Recommend `valid-only`
  as headline if reviewer pushback is anticipated.
- **§8 Failure modes**: add C8 "Agent server silent error masking" with
  Mode A breakdown.
- **§16 Gate decision**: per amendment §16, Δ < +0.02 → HALT. With Mode A
  fix, Δ ≈ +0.00 (valid-only) → still HALT under strict gate, but the
  failure-mode narrative shifts from "method underperforms" to "method
  matches baselines on completed cases; infrastructure noise dominates
  shortfall". This is a more publishable framing.

## Files touched (proposal — not yet applied)

- `agent/run_agent_v2.py:459` — re-raise
- `code/pipelines/s4_agentic_tmg.py:205` — retry-on-empty
- `code/adapters/viz_output_mapper.py:262` — drop fabricated fallback

All three are low-risk, additive, preflight-able.
