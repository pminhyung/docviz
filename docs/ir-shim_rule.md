# `sft-gen-ir-shim` authoring rules

Operating manual for any change landing on the `sft-gen-ir-shim` branch.
This branch is the SFT data-generation working copy: it inherits from
`master` and adds only the variants that SFT (or multimodal QA, or
chat-template workarounds) actually require.

Read alongside:
- `docs/master_rule.md` — the production-side rules. **Every rule there
  applies here unless this file explicitly overrides it.**
- `docs/cross-branch-divergence.md` — what differs between branches and
  why.
- `exaone/docqa_tools/_policy.md` — the docqa-surface flow contract.

## Founding principle

**ir-shim = master + necessary variants only.** Before adding a new file
or diverging from master, ask: *is this variant strictly required for
SFT, mm_docqa, or the v19 chat-template workaround?* If the answer is
"no", land the change on master instead and let it flow back via the
shared-logic sync rule.

The legitimate reasons for divergence are enumerated in
`cross-branch-divergence.md` §2:

1. idx-only schema (model never sees raw paths/UUIDs).
2. Mode A vs Mode B (`HERMES_DOC_SOURCE=local|remote`).
3. `mm_docqa` mode + multimodal/page-layout tools.
4. The whole `exaone/sft_gen/` SFT pipeline.
5. v19 chat-template adapter (Qwen3 empty-think bug).
6. `{language}` placeholder pin + `language` kwarg.
7. mm_docqa-side auxiliary writers (`write_vlm_*_log`).

Anything you cannot map to one of these seven needs a discussion before
landing.

## Hard rules (CRITICAL — block the PR if violated)

All HARD rules from `master_rule.md` apply (no core edits, unit tests,
smoke triggers, JSON-string contract, profile-safe paths,
`run_tests.sh`). The additional rules below are ir-shim-specific.

H1. **Do not break shared-logic byte-identity.** The files listed in
   `exaone/docqa_tools/_policy.md` "Shared logic files" must be
   byte-identical to master's copy. After editing any of them, copy the
   result to master in the SAME patch series. If a manual merge is
   needed, you broke the contract.

H2. **Do not regress master functionality on ir-shim.** Concrete
   examples seen in practice:
   - master's `taskbot` mode ships `prompts/identities/taskbot.txt` +
     `prompts/style/taskbot.txt` with strict "no web fallback" wording.
     Don't collapse taskbot's identity into docqa's prompts on ir-shim.
   - master's `.gitignore` carries harness-tracking ignores
     (`.harness/`, `.worktrees/`, `docs/active`). Keep them on ir-shim's
     `.gitignore` too.

H3. **Mode A code must be cleanly separable from Mode B.** All Mode A
   logic lives behind `is_local_mode()` from
   `exaone/docqa_tools/_doc_source.py`. Do not sprinkle
   `os.getenv("HERMES_DOC_SOURCE") == "local"` checks inline; route
   through the helper.

H4. **Mode B == production master behaviour, byte-for-byte where
   possible.** Mode B is the path that should match what `master`
   does in production. If a bug is found on master, fix it there
   first and propagate the same fix to ir-shim's Mode B in the
   sibling commit.

## Strong rules (HIGH — fix in the same PR)

S1. **Idx-only interface stays idx-only on the wire**. The prompts, the
    schemas, and the envelopes that the model sees must never expose
    `file_id`, `fid`, or raw `file_path`. The internal cache stores the
    fid; the model sees `document_idx` only. Any new tool or prompt
    that breaks this rule must justify it in `_policy.md`.

S2. **mm_docqa is a layered extension, not a parallel system**. Add
    to `qa_modes.py`, add prompts under `prompts/{identities,style}/`,
    add tools under `exaone/visual_tools/` and the per-extension
    `exaone/<ext>_tools/`. Do not duplicate docqa core; reuse it.

S3. **SFT pipeline code lives in `exaone/sft_gen/`**. Do not leak SFT
    concerns into the agent loop, the cache, the IR client, or the
    handlers. The handlers must work identically whether or not the
    SFT pipeline is the caller.

S4. **The `_policy.md` "Document flow policy (background)" docstring
    section** must be present in every docqa/parsing handler module.
    Missing on ir-shim's `handle_doc_search.py`,
    `handle_get_document_chunks.py`, `handle_read_full_document.py`
    today — these need to be added back.

S5. **The v19 adapter is opt-in.** It must be safe to set
    `EXAONE_V19_ADAPTER=0` (or unset the env entirely) and have the
    agent run unmodified through the standard openai client. If
    disabling the adapter breaks anything, you broke the contract.

S6. **Auxiliary tracer extensions go after `write_rd_extract_log`.**
    Everything from the start of file through `write_rd_extract_log`
    is shared with master and must stay byte-identical. mm_docqa-side
    writers (`write_vlm_*_log`) live after that line and are ir-shim
    only.

## Process rules (PREFER — apply unless there's a reason not to)

P1. **Branch in the same commit message** when you mirror a master
    change here: cite the master SHA. Example:
    `fix(docqa): mirror master 7b4f4882 review fixes (rehydrate + probe)`.

P2. **Before adding an "ir-shim only" file**, check whether master
    could benefit from it too. Examples that should have been on
    master but were not:
    - BRAVE_KEYS rotation in `tools/web_tools.py` — generic concurrent-
      worker improvement.
    - vendor sampling preset in `exaone/config.py` — Qwen3-family
      defaults are correct outside SFT too.
    If the helper is generic, land it on master and let ir-shim
    inherit it via the shared-sync cycle.

P3. **The shim-side selector (`exaone/sft_gen/shim/selector_client.py`)
    is a different microservice from the lgair IR.** Don't conflate
    them; never homogenise their wires.

## What to do before pushing

1. Run `scripts/run_tests.sh tests/exaone/unit/` and paste into the PR
   body.
2. Run both preflight modes:
   ```bash
   PYTHONPATH=. EXAONE_PARSED_ROOT=/poc/docai/out python scripts/preflight_modes.py local
   PYTHONPATH=. EXAONE_FILES_API_KEY=... EXAONE_IR_URL=... \
     python scripts/preflight_modes.py remote
   ```
   Confirm `completed=True` on both, and that no `Tool execution failed`
   appears in the tool-call sequence for either.
3. `diff exaone/docqa_tools/_ir_client.py <master worktree>/exaone/docqa_tools/_ir_client.py`
   and confirm zero-byte diff. Repeat for `_doc_cache.py`, `_policy.md`,
   and the shared portion of `auxiliary_tracer.py`.
4. If your change is generic (not SFT-specific), open a parallel master
   PR with the same fix.
5. Re-read `cross-branch-divergence.md` §3.3 to confirm you did not
   introduce more drift.
