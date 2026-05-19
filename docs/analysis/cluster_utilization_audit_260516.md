# Cluster Utilization Audit — 2026-05-16 09:00 launch readiness

**Date**: 2026-05-15 (audit) for 2026-05-16 09:00 launch
**Cluster**: Qwen3.5-397B-A17B-FP8, 9 hosts (10.1.211.148 + 163-170, all :8000)
**Audit scope**: read-only; no code modified.

---

## 0. Live state at audit time

Probed `/v1/chat/completions` (real inference, not just `/v1/models`):
**9/9 hosts return 200 with valid completions NOW.** Cluster already recovered.

Declared background PIDs 2494244/2512327 already exited. `B6_NoSAO` n=265
done (24 fails ~9%, well under 82.6% threshold). `B6_NoCIS` only 3/265 —
chain died. Treat as Job 0 to finish (§C).

---

## A. Bottleneck inventory

| # | Component | Bottleneck | Verdict | Recommended |
|---|---|---|---|---|
| A1 | Agent server uvicorn `--workers 1` (port 9037) | `AgentHandler._executor = ThreadPoolExecutor(max_workers=4)` caps in-flight at 4 (`handlers.py:54`) | Multi-worker uvicorn safe — `AgentV2Runner` + `trace_collector` are per-request (`run_agent_v2.py:247`); `SessionManager` is thread-safe (`session_manager.py:65-69`); we don't pass `session_id` so per-worker singletons don't matter | Either `--workers 4` (4 procs × executor=4 = 16) OR raise `AgentHandler.max_workers` to 16 (handlers.py:47). **Latter is the bigger lever.** |
| A2 | Sticky reasoner URL per S4 instance (`s4_agentic_tmg.py:146`) | `_next_reasoner_url()` (line 95) advances module-global cursor under lock; each `pipeline_factory()` per task creates a new instance + binds 1 host for the whole `.run()` (~9 LLM calls) | With `--s4-workers=N` and 9 hosts, workers map to host indices `0..N-1 mod 9`. Effective parallelism = N concurrent agent calls; spreads across all 9 hosts only when N ≥ 9 | **`--s4-workers >= 9`** (see A4) |
| A3 | Cooldown (`agent_client.py:364` `_HOST_COOLDOWN_SECONDS=30.0`) — **`QwenDirectClient` only**, NOT S4 sticky URL | `_next_healthy_base` (line 398) skips cooldowned hosts; round-robin still advances 1 slot per call → 1 sick host doesn't idle the other 8 | No under-utilization. (S4 has its own retry-on-different-host at line 268.) | **No change** |
| A4 | `--s4-workers 1` default (`run_prototype.py:273`) | Each B6 V4_cons request fans out to ~9 internal LLM calls (1 doc-summary + up to `n_steps_max=8` reasoning + 1 generate_viz tool call sharing sticky host). 1 worker oversubscribes 1 host, idles 8 | With N workers Σ in-flight ≤ 9N, distributed across `min(N, 9)` hosts | **`--s4-workers=12`** (12 instances → 9 distinct hosts covered, 3 doubled; vLLM batches; safely under A1 ceiling). Cap at 16. |
| A5 | Judge `--checklist-workers 3` / `--score-workers 3` (`run_judge.py:210-211`) | Both hit the SAME vLLM cluster via `QwenDirectClient` (lines 115, 152). 1 LLM call per request. No tool fan-out. No separate judge model. | With 9 hosts × 1 call/request, a worker holds 1 host ~3-15s | **`--score-workers=18`, `--checklist-workers=9`** |
| A6 | S1/S7/B1-B4 share `QwenDirectClient` round-robin state? | Each pipeline factory builds its own `QwenDirectClient()` (s1:61, s7:158, b1-b4 ~207). `_run_strategy_pool` creates a fresh pipeline per task (`run_prototype.py:212`). Cursor + cooldowns are INSTANCE-local — workers don't share them | Distribution is statistically even (cursor cycles); cooldowns don't propagate across workers. Acceptable. | **`--s1-workers=18`** |

**Sticky-binding pitfall**: `_next_reasoner_url()` (s4_agentic_tmg.py:95)
has NO cooldown — if host 165 dies, every new instance landing on its
slot fail-retries once (line 268). At workers=12, ~1/9 of records take
+3s if any host is sick. Acceptable.

---

## B. Concurrent-job feasibility

All four jobs share the same 9-host vLLM cluster (no separate judge model).

| Pair | Contention | Decision |
|---|---|---|
| (1) 3-seed bulk × (2) Plot2Code retry | Same agent server `AgentHandler._executor` | **Serial** — (1) at `--s4-workers=12` already saturates. Slot (2) between seeds. |
| (1) × (3) Text2Vis judge | (3) is direct `QwenDirectClient`, no agent executor contention | **Parallel OK** at `--s4-workers=12` + `--score-workers=6` |
| (1) × (4) re-judge | Both direct, low marginal load | **Serial preferred**; re-judge after (1) done |
| (2) × (3), (2) × (4) | Different paths / low load | **Parallel OK** |
| (3) × (4) | Different `--out` paths (text2vis vs prototype) | **Parallel OK** |

**Recommended order**: 09:05 restart server → 09:10 finish B6_NoCIS (~30 min @ workers=12) → 09:40 (1) seed=43 ‖ (3) Text2Vis judge → ~14:30 (1) seed=44 ‖ (2) Plot2Code retry → ~19:00 (4) re-judge if applicable.

---

## C. Concrete launch plan

Common env (export once per shell):
```bash
cd /ex_disk2/mhpark/poc/docviz
export QWEN_HOSTS="10.1.211.148:8000,10.1.211.163:8000,10.1.211.164:8000,10.1.211.165:8000,10.1.211.166:8000,10.1.211.167:8000,10.1.211.168:8000,10.1.211.169:8000,10.1.211.170:8000"
export DOCVIZ_HOST_MODE=multi
export DOCVIZ_AGENT_URL=http://localhost:9037   # agent_client.py:26 default is 9024
```

### Job 0 (precondition): finish B6_NoCIS (262 left)
```bash
python -m code.run_prototype --strategies B6_NoCIS --s4-workers 12 \
  --raw outputs/prototype/viz/raw.jsonl
```

### Job 1: Three-seed reporting (seeds 43, 44)
**BLOCKER**: no `--seed` CLI flag exists; `PAPER_DEFAULT_SEED=42` is
hardcoded (agent_client.py:64) and consumed in 7 pipeline files
(b1-b4, s1, s7, agent custom_rules string). Three options, ranked:
1. **Add `QWEN_SEED` env override at agent_client.py:64**
   (`PAPER_DEFAULT_SEED = int(os.environ.get("QWEN_SEED", "42"))`).
   1-line patch; touches 0 V4 design surface. Then:
   ```bash
   QWEN_SEED=43 python -m code.run_prototype \
     --strategies B1,B2,B3,B4,S1,S7_SelfRefine,S4_TMGv4_consolidated \
     --s4-workers 12 --s1-workers 18 \
     --out outputs/prototype/viz/all_seed43.json \
     --raw outputs/prototype/viz/raw_seed43.jsonl --force
   # then seed=44 with all_seed44.json / raw_seed44.jsonl
   ```
2. Pass `--seed` through CLI → run_prototype → pipeline factories. ~20 LOC.
3. Run as-is with seed=42 only and report n=1 (violates §13).

Choose (1). Estimated wall: 7 baselines × 265 / (workers throughput) ≈
4-5h per seed; total ~10h matches state.md §13 estimate.

### Job 2: Plot2Code B6 V4_cons retry (after 5-record preflight)
```bash
python -m code.run_prototype --strategies S4_TMGv4_consolidated \
  --bundles data/prototype/eval/plot2code/bundles.json \
  --queries data/prototype/eval/plot2code/queries.json \
  --out outputs/prototype/eval/plot2code/viz/all.json \
  --raw outputs/prototype/eval/plot2code/viz/raw.jsonl --s4-workers 12 --force
```

### Job 3: Text2Vis Qwen judge (700 records)
```bash
python -m code.judge.run_judge --viz outputs/text2vis/viz/all.json \
  --bundles data/prototype/eval/text2vis/bundles.json \
  --out outputs/text2vis/judge_scores/all.json \
  --checklist-cache outputs/text2vis/judge_scores/checklists.json \
  --raw outputs/text2vis/judge_scores/raw.jsonl \
  --checklist-workers 9 --score-workers 18
```

### Job 4: Layer A re-judge (only if SQQ fix applied)
```bash
cp outputs/prototype/judge_scores/all.json{,.bak_pre_rejudge_$(date +%s)}
python -m code.judge.run_judge --score-workers 18 --checklist-workers 9 --force
```

---

## D. Pre-launch checklist (BEFORE 9am)

| ✅ | Action | Command |
|---|---|---|
| 1 | Cluster health probe (real inference, not /v1/models) | `for h in 148 163 164 165 166 167 168 169 170; do curl -s -m 6 -o /dev/null -w "$h:%{http_code} " http://10.1.211.${h}:8000/v1/chat/completions -H "Authorization: Bearer EMPTY" -H "Content-Type: application/json" -d '{"model":"Qwen3.5-397B-A17B-FP8","messages":[{"role":"user","content":"hi"}],"max_tokens":2}'; done; echo` |
| 2 | Restart agent server. Live PID 3119300 (started 14:57) PREDATES the uncommitted skip_doc_step edits to handlers.py/schemas.py/run_agent_v2.py (`git diff --stat HEAD`) — B6_NoCIS WILL silently no-op without restart. | `kill 3119300 && cd /ex_disk2/mhpark/poc/docviz && nohup uvicorn agent.api.server:app --host 0.0.0.0 --port 9037 --workers 1 --log-level info > /tmp/agent_server.log 2>&1 &` |
| 3 | Disk: 92% used / 1005 GB free on `/ex_disk2`. Plenty for tomorrow. Optional: `mv core.108* core.140* /tmp/` (~2.1GB+ crash dumps in repo root). | `df -h /ex_disk2` |
| 4 | Backup before any re-judge | `cp outputs/prototype/judge_scores/all.json{,.bak_pre_rejudge_$(date +%Y%m%d)}` |
| 5 | Sidecar dir: 12 stale files in `/tmp/v4_viz_outputs/` — clear to avoid stale-read | `rm -f /tmp/v4_viz_outputs/*` |
| 6 | Verify tool path + oneshot pool | `python3 -c "from code.pipelines.s4_agentic_tmg import _GENERATE_VIZ_TOOL_PATH as p; print(p.exists())"; ls -la /ex_disk2/mhpark/poc/docviz/code/agent_tools/oneshot_pool.json` |

---

## E. Risks & guardrails

| Risk | Mitigation |
|---|---|
| Repeat 82.6% B6_NoSAO pollution (cluster flake → silent empty `final_answer` per `run_agent_v2.py:459`) | s4_agentic_tmg.py:263 retries on tokens=0+empty. ALSO: tail `viz/raw.jsonl`; abort if rolling fail-pct > 30% on last 30 records. |
| Mode B (agent reasons but never invokes `generate_viz`) | Accept; per state.md §11.12 not Fix-1+2+3-addressable. Not a launch blocker. |
| Workers=12 imbalance (3 hosts double-bound) | Acceptable; vLLM batches concurrent requests. |
| **Closed-API spend** | **$0 confirmed.** No queued job touches `claude -p` or paid models. `code/adapters/agent_client.py:59` sets `DEFAULT_REASONER_KEY="EMPTY"` so `_resolve_admin_keys` (handlers.py:347) never fires. |
| Resume safety | `_load_existing` (run_prototype.py:131) and `_load_existing_scored` (run_judge.py:74) skip done `(query_id, strategy)`. `--force` only drops the SELECTED strategy (run_prototype.py:323). Idempotent; don't `--force` blindly across strategies. |
| **Three-seed plumbing missing** | seed=42 hardcoded in 7 files (PAPER_DEFAULT_SEED, agent_client.py:64). 1-line `QWEN_SEED` env-override patch needed BEFORE 9am — mechanical, doesn't touch V4 design surface (custom_rules / generate_viz tool prompt / one-word final_answer per 2026-05-11 MUSTs). |
| **Default `DOCVIZ_AGENT_URL` mismatch** (default 9024; live server 9037) | Always export `DOCVIZ_AGENT_URL=http://localhost:9037` at top of every shell. |

---

## F. V4 design-feedback compliance check

Confirmed NO recommendation modifies:
- V4 `custom_rules` (`V4_POOL_EXPOSURE_RULE` in `code/pipelines/tmg.py`)
- `generate_viz` tool internal prompt (`code/agent_tools/generate_viz.py`)
- one-word `final_answer` constraint (rule 17/18 in V4_POOL_EXPOSURE_RULE)

All recommendations are infrastructure (worker counts, env vars, restart,
seed env). No prompt or design-surface changes. Per
`docs/active/tracks/feat-source-loaders/feedback.md` 2026-05-11 MUSTs.
