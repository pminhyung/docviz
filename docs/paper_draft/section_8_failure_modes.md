# §8 Failure Modes and Negative Findings (v0.3 draft)

> Session-internal findings (C5/C6/C7 from feat/source-loaders track)
> + Layer-B-3 Plot2Code held-out negative finding.

## 8.1 C5 — Naive Placeholder One-Shot Suppresses Entity-Grounded Labeling

**Observation** (from v0.2 → v0.3 transition): A first-pass V4 one-shot
pool exposed a single generic exemplar to the model, with placeholder
entity labels. The model copied the *style* of the placeholder (generic
"Item A", "Group 1") rather than grounding labels in source entities.

**Evidence**: V1 − V0 paired Δ on the 60-record QG-MDV (Qwen3.6-27B
prior measurement): faithfulness +24.3%p on the drop-subset,
Cohen's d_z = +0.90, BCa 95% CI [+0.18, +0.31].

**Resolution**: V4_consolidated (B6) uses 10 separate exemplars (one
per viz_type), each with rich entity-realistic content. The
generate_viz tool prompt explicitly tells the model to use the
exemplar's SYNTAX only, not its CONTENT — "Do not carry over the
example's domain, title format, structural layout, color palette, or
level of abstraction; pick whatever is most useful for the brief
below" (Fix #4 patch).

**Paper position**: Negative finding of v0.2 → motivates v0.3's TMG
Pillar 2 specification.

## 8.2 C6 — Generate-viz Tool Adoption is Brittle Without Override

**Observation** (session 2026-05-11): Same V4 architecture worked on
Qwen3.6-27B but failed on Qwen3.5-397B (0/3 adoption) — the larger
model's `search → final_answer` prior over-rode the rule-17 "must
invoke generate_viz" directive.

**Fix mechanism** (4-fix combo, ablated):
1. Rule 17/18 strengthened to explicit hard precondition with
   "<final_answer> is BLOCKED until generate_viz invoked"
2. FINAL_ANSWER_PATCH removed — was a recency-bias source pulling the
   model back to citation-style output
3. Multi-doc bundle refactor — `bundle_to_docai.py` emits N JSON files
   per source doc (vs 1 concat'd file) so the doc-step doesn't
   short-circuit the agent's retrieval need
4. generate_viz prompt forbids tooltip callbacks / JS function strings
   beyond exemplar

**Validation** (paired 8-sample re-run, 2026-05-11):

| Axis | OLD (Q3.6-27B) | NEW current (bug) | **NEW fixed** | Δ(fix−OLD) |
|---|---|---|---|---|
| overall | 0.852 | 0.837 | **0.944** | **+0.092** |
| faithfulness | 0.781 | 0.891 | **0.922** | **+0.141** |
| coverage | 0.938 | 0.917 | 0.958 | +0.021 |
| type | 0.813 | 0.750 | **0.938** | +0.125 |
| search_query_quality | 0.875 | 0.792 | **0.958** | +0.083 |

**Paper position**: documented as engineering-side mechanism — the
B6 method requires explicit override of the default LLM final-answer
priors. Per amendment §13 critical principle: B6 needs all 4 fixes for
deployment.

## 8.3 C7 — Held-Out Single-Doc Generalization

**Observation** (Plot2Code preflight, this session): B6 exec_rate on
Plot2Code is 0.20 vs B5/B7 at 1.00/0.80. The multi-doc-specialized
agent architecture (multi-doc bundle adapter, doc-step summary,
search-then-generate_viz loop) is brittle when given a single-doc
single-instruction input.

**Evidence**: 5-record preflight on Plot2Code (Layer B-3):

| Baseline | exec_rate | CLIPScore (Hessel) | Mean duration |
|---|---|---|---|
| B5 Direct-LLM | 1.00 | 0.601 | 7.0s |
| B7 SelfRefine | 0.80 | 0.567 | 27.6s |
| **B6 (Ours)** | **0.20** | 0.607 | 82.2s |

When B6 *does* execute, CLIPScore (0.607) is comparable to others
(0.567-0.627 range). The brittleness is invocation-rate, not output
quality per se.

**Paper position**: This is the **Tier-1 framing direction**. We do
NOT claim Plot2Code SOTA. We claim multi-doc QG-MDV SOTA (Layer A).
Held-out single-instruction settings are out-of-distribution for our
method; specialists win on their home turf (within 5-7%p), but we win
on the multi-doc setting they were not designed for. Tier-1 home-turf
reference is the appropriate framing per amendment §10 footnote
("Tier 1 only — specialists run only on home turfs to provide the
reference 'competitive within 5-7%p' benchmark").

## 8.4 C8 — Agent Server Silent Error Masking

Layer A V4_cons (B6) full-set mean (0.735, n=265) versus valid-only
mean (0.851, n=216) shows a 0.116 gap driven by 40 failure records
(15.1%). Root-cause analysis (`docs/analysis/v4_cons_fail_root_cause.md`)
classifies them into four modes:

| Mode | n | % | Pattern | Mechanism |
|---|---|---|---|---|
| A | 26 | 65 | duration ≈ 2 s, tokens=0 | upstream LLM ConnectError / 401 caught silently by agent server's `except Exception` (`run_agent_v2.py:459`); handler returns 200 OK with empty `final_answer` |
| B | 10 | 25 | 100–400 s, 10K–120K tokens | model reached `n_steps_max=8` without emitting the `generate_viz` tool-call structured block |
| C | 3 | 7.5 | 600 s, tokens=0 | client-side timeout (upstream LLM hang) |
| D | 1 | 2.5 | 200 s + HTTP 400 | server-side validation reject of one-word `final_answer` (Plot2Code single-doc edge case) |

The artifactual `viz_type=mermaid_flowchart` label on 36/40 fails is a
mapper-side fallback (`viz_output_mapper.py:262 fallback_viz_type=
"mermaid_flowchart"`), not the agent's chosen type. Real per-fail
viz_type distribution is unrecoverable without re-running.

**Implication.** Mode A is an infrastructure artifact, not a method
failure. Specialist baselines (B1–B5, B7) do not exhibit it at the same
rate because they route via `QwenDirectClient` which has built-in 30 s
host cooldown + 3 s retry-once on transient errors (`agent_client.py:344`).
The agent server, in contrast, currently masks reasoner-subprocess
failures as 200 OK. A client-side retry-on-empty patch
(`s4_agentic_tmg.py:205`) plus a server-side re-raise in the agent loop
exception handler is expected to recover ~80% of Mode A based on the
preflight protocol described in the root-cause document.

For paper reporting we therefore present V4_cons under two cells:
- *full*: 0.735 (n=265) — published as the unfiltered headline
- *valid-only*: 0.851 (n=216) — published as the infrastructure-corrected
  reference under §16 reviewer-defense framing

Both cells fall below amendment §16's +0.02 gate vs the best baseline
(S1_Direct, S7_SelfRefine = 0.880), and the gate decision is HALT in
either reading. The implications for method positioning are discussed
in §11 future work and §16 R8.

## 8.5 Implications for Method Direction

- C5: validated TMG Pillar 2 (10 exemplars, syntax-only).
- C6: validated explicit rule-override + multi-doc bundle as core
  architectural requirements.
- C7: motivates Week-1 work — generalist mode that detects single-doc
  input and degenerates to B5-style single-call (vs the full 4-step
  agent loop). Out of v0.3 prototype scope; documented in §11 future
  work.
- C8: motivates infrastructure hardening (retry-on-empty client patch
  + re-raise in server exception handler) as a v0.3-iteration fix
  prerequisite for any future re-batch. Until applied, V4_cons full-set
  cells must be reported alongside valid-only equivalents.
