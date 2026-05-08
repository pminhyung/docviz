# Week 0 — Progressive Log

## 2026-05-08 — Day 1 (PR1 `feat/week0-bootstrap`)

### Summary
Bootstrap layer landed. `code/` scaffolding, paper schema dataclasses,
agent HTTP client, Bundle → docai serializer, agent-response → VizOutput
mapper, cost tracker, end-to-end smoke test all in place.

### Decisions (locked in)
- Backbone for Week 0: **Qwen3.6-27B** vLLM (3 hosts at :9101/9102/9103, TP=4 each, GPU 4-15, `max_model_len=131072`).
- Multi-doc serialization: **LongBench-style concat into a single docai dict-of-pages JSON** (one Doc per page). Avoids the agent API's 2-doc cap entirely.
- Judge for Week 0 prototype: **homo-judge** (Qwen3.6-27B for both checklist gen and scoring). r<0.5 ⇒ JUDGE-FIX path with a second open-weight model.
- Closed APIs (GPT-5 / Claude / Gemini) deferred to the final validation stage; user will provide keys at that point.
- Language: `en` only across all 4 sources (HotpotQA / MultiNews / arXiv / 10-K).

### Verification
- 21/21 unit-level checks (`code.adapters.*`, `code.pipelines.base`, `code.utils.cost_tracker`) pass.
- E2E smoke (`code.scripts.smoke_test_pr1`): 4-step agent run on a 449-char synthetic 2-doc bundle, 12,944 tokens out, 303 s wall, VizOutput mapper produced a populated object (sub_queries=2, retrieved_chunks=1, no errors). DSL block fell back to mermaid_flowchart since no custom tool was loaded — expected for PR1; PR4 wires the proper viz tool path.

### Risks observed during PR1
- `RunResponseV2.total_tokens` reports a single number (no in/out split) — `viz_output_mapper` records it under `tokens_out` for now. If split is needed later, parse from `RunResponseV2.train_sample` or `trace`.
- The agent fell into the OpenAI public API code path on first attempt because a non-empty `reasoner_api_key` is required even for vLLM endpoints — `AgentClient` now passes `"EMPTY"` to satisfy the validator.
- `core/llm_pool` import in `examples/diagram/diagram_tools.py:1360` is still dangling; will be re-routed via `core.model_router` in PR4.

### Tomorrow
PR2 — 4 source loaders (HotpotQA, MultiNews, arXiv, 10-K), seed=42, en-only,
producing 30 bundles validated against `Bundle` schema.
