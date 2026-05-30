# Claude project instructions — EXAONE on Hermes (sft-gen-ir-shim)

This branch hosts the EXAONE SFT data-generation pipeline layered on the
Hermes-Agent fork. Reference docs in this tree:

- **`AGENTS.md`** (~990 lines) — full upstream developer guide: project
  structure, Hermes core (`run_agent.py`, `cli.py`, `gateway/`, `tools/`,
  `model_tools.py`, `toolsets.py`), plugin / skill / kanban / cron /
  curator systems, profiles, testing policy.
- **`test_rule.md`** — upstream testing policy (1차 unit + 2차 unit +
  optional smoke). MR precondition.
- **`docs/ir-shim_rule.md`** — authoring rules specific to this branch.
  **Read before touching anything under `exaone/`.**
- **`docs/master_rule.md`** — authoring rules for the production branch.
  All HARD rules there also apply here unless `ir-shim_rule.md`
  overrides them.
- **`docs/cross-branch-divergence.md`** — what differs between `master`
  and `sft-gen-ir-shim` and why; outstanding violations to address
  before MR.
- **`exaone/docqa_tools/_policy.md`** — docqa surface flow contract +
  shared-logic file table. Read before editing
  `exaone/docqa_tools/`, `exaone/parsing_tools/`, or the shared
  portion of `exaone/auxiliary_tracer.py`.
- **`exaone/sft_gen/SFT_DATA_GUIDE.md`** (~620 lines) — SFT record
  schema, loss-masking, tool-call / citation rules, structural
  validity, aux-task trajectory handling.

## When to read the full guides

- **`docs/ir-shim_rule.md` + `docs/master_rule.md`** — first read for any
  change. The branch-rule files cite AGENTS.md / test_rule.md sections
  by line number and tell you which parts apply.
- **`docs/cross-branch-divergence.md`** — read when you are about to
  add, delete, or modify a file that differs between branches, or before
  opening an MR.
- **`AGENTS.md`** — when the rule files send you here, or before any
  non-trivial change to Hermes core or the plugin / skill / gateway
  surfaces.
- **`test_rule.md`** — before committing tests; before opening an MR.
- **`SFT_DATA_GUIDE.md`** — when working on SFT dataset code:
  `exaone/sft_gen/`, `exaone/batch_runner*.py`,
  `exaone/auxiliary_tracer.py` mm_docqa portion, `exaone/agent.py`
  (system-prompt assembly), or any `tests/exaone/`. The
  `sft-data-guide` skill auto-loads this content; invoke it (or read
  the file directly) before writing dataset filters / validators / new
  tool-result envelopes.

## Always-on rules (apply to every code change in this repo)

1. **Tests run via `scripts/run_tests.sh`, not raw `pytest`.** The wrapper
   enforces CI parity (unset API keys, `TZ=UTC`, `LANG=C.UTF-8`, `-n 4`).
   Direct `pytest` diverges in five known ways → "works locally, fails in
   CI."
2. **Don't break prompt caching.** No mid-conversation mutations of past
   context, toolsets, memory, or system prompts. Cache-breaking changes
   must be opt-in (`--now` flag) with deferred default. The only sanctioned
   mutation point is context compression.
3. **Use `get_hermes_home()` (code) / `display_hermes_home()` (user-facing
   strings) for `HERMES_HOME` paths.** Never hardcode `~/.hermes` —
   breaks profiles.
4. **Don't write change-detector tests.** Tests must assert relationships
   / invariants (e.g. "every catalog entry has a context length"), not
   snapshots (e.g. `assert "gemini-2.5-pro" in models` or `len(...) == 8`).
   See `AGENTS.md` § Testing for the rationale + examples.
