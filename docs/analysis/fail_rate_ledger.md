# Fail Rate Ledger — All Strategies (v0.3 prototype)

Maintained as Layer A + Layer D + Layer B runs complete. `fail` = records
with empty `viz_dsl` (< 20 chars) in `outputs/prototype/viz/raw.jsonl`.

Updated: 2026-05-13 (Layer D B6_NoTMG just completed; B6_NoSAO running).

## Layer A baselines (current-qid filtered, n=265)

| Strategy | Total | Fails | Fail % | Mean overall (full) | Mean overall (valid-only) |
|---|---|---|---|---|---|
| B1_MatPlotAgent | 265 | 0 | 0.0% | 0.789 | 0.789 |
| B2_NVAGENT | 265 | 0 | 0.0% | 0.786 | 0.786 |
| B3_CoDA | 265 | 0 | 0.0% | 0.825 | 0.825 |
| B4_ViviDoc | 265 | 0 | 0.0% | 0.856 | 0.856 |
| S1_Direct (B5) | 265 | 0 | 0.0% | 0.880 | 0.880 |
| S7_SelfRefine (B7) | 265 | 0 | 0.0% | 0.880 | 0.880 |
| **S4_AgenticTMGv4_consolidated (B6)** | 265 | 39 | **14.7%** | 0.735 | 0.849 |

B6 is the only strategy with non-zero fail rate. Specialist baselines
(B1–B4) and Direct/SelfRefine (B5/B7) use `QwenDirectClient` with
built-in cooldown+retry; B6 routes via the agent server which has the
§8.4 C8 silent error masking.

### V4_cons fail mode breakdown (n=39, from `v4_cons_fail_root_cause.md`)

| Mode | Count | % of B6 fails | Mechanism |
|---|---|---|---|
| A: agent-loop silent crash | 26 | 65% | upstream LLM ConnectError → 200 OK + empty final_answer |
| B: n_steps_max exhausted | 10 | 25% | model didn't invoke generate_viz in 8 steps |
| C: 600s timeout | 3 | 8% | client-side timeout |
| D: HTTP 400 reject | 1 | 3% | final_answer validation reject |

### Fix 2 preflight result (5 records, retry-on-empty)

- 4/5 OK (80% recovery rate)
- 1/5 timeout (ReadTimeout 600s on retry host too)
- Recovered records' actual viz_types: 3 × mermaid_timeline, 1 ×
  chartjs_grouped_bar (NONE flowchart — confirms mapper fallback artifact)

## Layer D pillar ablation (PAUSED 2026-05-13 — resume after Layer B)

| Variant | Total | Fails | Fail % | Status |
|---|---|---|---|---|
| **B6 Full (= V4_cons)** | 265 | 39 | 14.7% | done (Layer A) |
| **B6 −TMG** | 265 | 70 | **26.4%** | **done 2026-05-13** |
| **B6 −SAO** | 46 / 265 | 38 | **82.6%** | **PAUSED — pollution (see resume guide)** |
| **B6 −CIS** | (deferred) | — | — | Week-1 (server flag not impl.) |

### NoTMG analysis

B6_NoTMG fail rate **26.4%** is 1.8× V4_cons's 14.7%. NoTMG uses the
plain S4_Agentic loop without V4 rule, so it produces DSL inline in
`final_answer` (no generate_viz sidecar fallback). Hypotheses:

1. **Same Mode A infrastructure noise** (~10%): agent server silent
   crash hits NoTMG identically.
2. **Plus DSL extraction failures** (~16%): without V4 rule guidance,
   model produces final_answer in formats `_extract_dsl_block` can't
   parse (e.g., prose explanation without ```code``` fence, JSON
   without `viz_type` field).

### B6_NoSAO pause snapshot (resume guide)

User direction (2026-05-13): pause Layer D, switch to Layer B first.

**Frozen state**:
- Records 1–46/265 of B6_NoSAO are persisted in `outputs/prototype/viz/raw.jsonl`
- Of those 46, **38 are fails (82.6%)** including 3 records that hit
  the 600s ReadTimeout
- Fail rate this high is **NOT trustworthy** — the agent server uptime
  is since 2026-05-11 + 9-host cluster may have degraded during run.
  Should NOT be analyzed as-is.

**Resume options** (when Layer D is resumed):

1. **Discard 46 polluted records + restart B6_NoSAO from scratch**
   (recommended):
   ```bash
   # Delete existing B6_NoSAO records before resume
   python3 -c "
   import json
   recs = []
   with open('outputs/prototype/viz/raw.jsonl') as f:
       for line in f:
           try: r = json.loads(line)
           except: continue
           if r.get('strategy') != 'B6_NoSAO':
               recs.append(line)
   with open('outputs/prototype/viz/raw.jsonl', 'w') as f:
       f.writelines(recs)
   # Also clean viz/all.json B6_NoSAO entries
   data = json.load(open('outputs/prototype/viz/all.json'))
   data = {k: v for k, v in data.items() if v.get('strategy') != 'B6_NoSAO'}
   json.dump(data, open('outputs/prototype/viz/all.json', 'w'))
   "
   # Verify agent server health before resume
   curl http://localhost:9037/health
   for h in 148 163 164 165 166 167 168 169 170; do
       curl -s -m 5 http://10.1.211.$h:8000/v1/models -o /dev/null -w "$h: %{http_code}\n"
   done
   # Re-arm the chain (only B6_NoSAO + B6_NoCIS remaining; NoTMG already done)
   QWEN_HOSTS=10.1.211.148:8000,10.1.211.163:8000,10.1.211.164:8000,10.1.211.165:8000,10.1.211.166:8000,10.1.211.167:8000,10.1.211.168:8000,10.1.211.169:8000,10.1.211.170:8000 \
   DOCVIZ_HOST_MODE=multi \
   DOCVIZ_AGENT_URL=http://localhost:9037 \
   PYTHONUNBUFFERED=1 \
   python -m code.run_prototype \
     --strategies B6_NoSAO,B6_NoCIS \
     --s4-workers 2 \
     > /tmp/layer_d_logs/03_resume.log 2>&1 &
   ```

2. **Resume from record 47** (keeps 46 polluted records): NOT
   recommended. Even if remaining records run cleanly, the 82.6%
   fail rate on records 1–46 would contaminate the per-source/per-type
   breakdown.

**Fix 2 has been broadened** in `s4_agentic_tmg.py:233-238` to apply
to ALL modes (not V4-only). The restart in option 1 will benefit
B6_NoSAO records from this fix.

**Layer D processes killed**:
- watcher PID 2719208 (parent — DEAD; prevented phase9 auto-launch)
- chain PID 2870040 (DEAD)
- run_prototype PID 2870044 (DEAD)

**Phase 9 chain was NOT triggered** — it would only fire after
layer_d_chain.sh completes, and we killed it mid-run.

## Earlier V4 study (separate Qwen3.6-27B sessions, NOT current data)

| Strategy | Total | Fails | Fail % |
|---|---|---|---|
| S4_AgenticTMG (V0 mode, Qwen3.6) | 60 | 1 | 1.7% |

V0 (placeholder one-shot, no generate_viz tool) achieved 1.7% fail rate
under Qwen3.6-27B with workers=1. Direct comparison with current data
not valid (different model, different infrastructure stability era).
Retained as a reference data point.

## Layer B-1 Text2Vis (n=100, complete 2026-05-13)

| Strategy | Total | Fails | Fail % | syntax_pass | Notes |
|---|---|---|---|---|---|
| S1_Direct | 100 | 0 | 0.0% | **97%** | top baseline |
| B3_CoDA | 100 | 0 | 0.0% | 96% | generalist analysis |
| B4_ViviDoc | 100 | 0 | 0.0% | 94% | |
| **B2_NVAGENT (home turf)** | 100 | 0 | 0.0% | 92% | NOT top; S1/B3/B4 above |
| S7_SelfRefine | 100 | 0 | 0.0% | 85% | |
| **B6 V4_cons (Ours)** | 100 | 9 | **9.0%** | **82%** | Fix 2 retry working (vs Layer A's 14.7%) |
| B1_MatPlotAgent (off-turf) | 100 | 0 | 0.0% | **0%** | matplotlib code on chart-spec task — total mismatch |

**Key observations**:
- B2 home-turf assumption is **incorrect** — S1_Direct, B3_CoDA, and
  B4_ViviDoc all beat B2 on syntax_pass. The "specialist owns home turf"
  Tier-1 framing needs revision: on Text2Vis (single-table chart spec),
  direct LLMs with simple chart-spec prompts already saturate the task.
- B1 has 0% syntax_pass — confirms cross-domain generalization is a real
  issue for matplotlib specialists.
- B6 (Ours) achieves 82% with 9% fails — improvement from Layer A's 15%
  fail rate, validating Fix 2's broadened retry-on-empty.
- B6's 82% vs S1's 97% gap is 15 percentage points; need judge-based
  evaluation to determine if score quality narrows the gap.

## Updates

- 2026-05-13 03:00 — Initial ledger created from Layer A + V4_cons
  preflight data.
- 2026-05-13 04:00 — B6_NoTMG completed; 70/265 fails (26.4%).
  B6_NoSAO paused at 46/265 (82.6% pollution — see resume guide).
- 2026-05-13 06:00 — Text2Vis bulk complete (100×7). B6 9% fails
  (improvement from Layer A 15%, Fix 2 retry working).
- 2026-05-13 06:30 — Plot2Code bulk launched (45 records × 7 strategies,
  expanding from existing 5-record preflight).
