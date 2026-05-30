# `master` authoring rules

Operating manual for any change landing on the production `master` branch.
This branch is the MR target for the LG-side
`/ex_disk2/mhpark/upload/chatexaone-agent-harness` repo, so every commit
needs to be defensible there.

Read alongside:
- `/ex_disk2/mhpark/upload/chatexaone-agent-harness/AGENTS.md` — the
  upstream developer guide. Not optional.
- `/ex_disk2/mhpark/upload/chatexaone-agent-harness/test_rule.md` — the
  testing policy that MRs must satisfy.
- `docs/cross-branch-divergence.md` — the audit summary; cite when an
  MR question comes up.
- `exaone/docqa_tools/_policy.md` — the docqa-surface flow contract.

## Hard rules (CRITICAL — block the MR if violated)

1. **Do not touch Hermes core**. No edits to `run_agent.py`, `cli.py`,
   `gateway/run.py`, `hermes_cli/main.py`, `tools/` (except adding a new
   `tools/<file>.py` that follows the AGENTS.md §"Adding New Tools"
   built-in pattern, and only when LG explicitly accepts that path),
   `toolsets.py::TOOLSETS` literal, `model_tools.py`. Fork-customization
   goes under `exaone/`.
2. **Every new module ships unit tests under `tests/exaone/unit/`**.
   File name pattern `test_<module>.py`. No external API calls — mock IR /
   parser / auxiliary client. `pytest tests/exaone/unit/` must pass
   locally. (test_rule.md L8-9, L115-121.)
3. **Smoke triggers fire smoke tests OR a documented PR-body skip**.
   Triggers: `qa_mode` / `toolset` / `enabled_toolsets` changes, new
   `auxiliary_*_*.json` file family, `_compress_context` /
   `auxiliary_finalizer.json` changes, `run_conversation` interface
   changes, `_handle_max_iterations` changes, `web_extract` summary path
   changes. (test_rule.md L15-39.) If `EXAONE_BASE_URL` is unavailable in
   CI, state that explicitly in the PR description.
4. **All handlers return a JSON string** via `tool_result(...)` or
   `tool_error(...)`. No raw `return json.dumps(...)`, no
   `return dict(...)`. (AGENTS.md L310.)
5. **All paths use `display_hermes_home()` / `get_hermes_home()`**. No
   hardcoded `~/.hermes`, no `Path.home() / ".hermes"`. (AGENTS.md L312-314.)
6. **Run `scripts/run_tests.sh`** (not raw `pytest`) before pushing. The
   wrapper enforces CI parity (unset API keys, `TZ=UTC`, `LANG=C.UTF-8`,
   `-n 4`). (AGENTS.md L903.)

## Strong rules (HIGH — fix in the same PR)

7. **Type-hint style is `X | None`, `dict[X, Y]`, `tuple[X, Y]`**. No
   `Optional[X]` / `Dict[X, Y]` / `Tuple[X, Y]` for new code. Mixing
   styles inside the same file is sloppy and visible in review.
8. **Every new `exaone/<package>/` module starts with
   `from __future__ import annotations`** when it carries any
   annotation; harmless to add when it doesn't.
9. **Module docstrings are 1-10 lines**. If a longer policy block is
   genuinely needed, link out to `exaone/docqa_tools/_policy.md` rather
   than inlining a multi-section essay. The upstream's house style is
   terse.
10. **Imports use stdlib / third-party / local grouping** with one
    blank line between groups. Move `import threading` to the top of
    the file — never `__import__("threading").Lock()` inline.
11. **Prompt files (`exaone/prompts/tools/*.txt`)** use `# Tool: <name>`
    as the first heading (one hash, upload convention). Not `### Tool:`.
12. **Prompts and schemas must agree**. If the prompt mentions a field,
    parameter, or downstream tool name, the schema and handler must
    actually expose it. Run `git grep -F "search(source=" exaone/prompts/`
    before committing — that exact string should not appear.
13. **Envelope shape consistency** across `handle_*` files in the same
    package. Either every handler carries `{"tool_name": ..., "results": [...]}`
    or every handler carries `{"success": True, "results": [...], "data": ...}`.
    Pick one; do not mix per-file.

## Process rules (PREFER — apply unless there's a reason not to)

14. **Plugin route first.** AGENTS.md §"Adding New Tools" L272-281
    favours `~/.hermes/plugins/<name>/plugin.yaml` for local/custom
    tools. The `exaone/` fork-customization route is fine when the tool
    is part of the EXAONE-specific bundle (docqa, taskbot, mm_docqa),
    but a single one-off helper belongs in the plugin tree.
15. **No tombstone comments.** Remove dead code rather than leaving
    `# NOTE: previous revision had X, removed because…`. Git history
    is canonical.
16. **No Unicode box-drawing dividers (`# ─── … ───`).** Use blank
    lines and short `#` comments. The upstream codebase does not use
    them.
17. **Cite `_policy.md` in shared-logic files**, not inline copies of
    the policy. The shared-file list lives in `_policy.md` "Shared
    logic files" — keep the in-file `## SHARED LOGIC` block under 10
    lines and link out.
18. **Avoid dead code introduced for cross-branch convenience.** If a
    helper exists on `master` only because `sft-gen-ir-shim` needs it
    and we want diff-zero, document it explicitly at the symbol with
    `# ir-shim only — kept here for diff-zero cherry-picks`.
19. **`requires_env` + `check_fn`** gate tools that depend on external
    services (IR, parser, Files API). Apply to every new
    service-dependent tool — not just the writer side. `list_documents`
    and `get_document_chunks` look local but functionally depend on a
    prior `parse_web_and_doc` which itself depends on parser/IR — gate them
    together with one shared check so the model sees a coherent
    catalog.

## Cross-branch sync rules (HIGH)

20. **Shared-logic files declared in `exaone/docqa_tools/_policy.md`
    must stay byte-identical between `master` and `sft-gen-ir-shim`**.
    Currently:
    - `exaone/docqa_tools/_policy.md`
    - `exaone/docqa_tools/_ir_client.py`
    - `exaone/docqa_tools/_doc_cache.py` (including the ir-shim-only
      `doc_to_page_dicts` helper that lives as dead code on master)
    - `exaone/auxiliary_tracer.py` up to and including `write_rd_extract_log`
      (everything below that line on ir-shim is mm_docqa-only and must
      NOT be added to master).

    When you edit any of these, mirror the change to the other branch
    in the SAME patch series. `cp` should be enough; if a manual merge
    is needed, you broke the contract.

21. **Intentional-divergence files** (declared in `_policy.md`
    "Intentional divergence") differ on purpose. Do not "fix" the
    divergence without first updating `_policy.md` to explain the
    new policy.

22. **CLAUDE.md** points to this file. Keep both files in sync when
    rules change.

## What to do before opening an MR

1. Run `scripts/run_tests.sh tests/exaone/unit/` and paste the result
   into the PR body.
2. Run `scripts/run_tests.sh tests/exaone/smoke/ -m smoke` if smoke
   triggers fired (see rule 3); otherwise add a short "smoke not run
   because <reason>" note to the PR body.
3. `git diff upload/main..HEAD --name-only` — sanity check that no
   file outside `exaone/` and `.gitignore` is in the list.
4. Re-read `docs/cross-branch-divergence.md` §3 to confirm no
   outstanding violations remain.
5. Cross-link in the PR description: this file, the
   `_policy.md` "Shared logic files" table, and the
   `cross-branch-divergence.md` divergence audit.
