# AGENTS.md

## Harness Rules (auto-managed)

The harness system emits structured markers in hook output. Act on them literally.

### Marker Protocol

Two marker types appear in hook output:

```
[HARNESS-METRIC key=value ...]      # data points; cite when explaining decisions
[HARNESS-ACTION tag] imperative      # what to do next; act on it
```

Whenever you see `[HARNESS-ACTION <tag>]`, invoke the corresponding skill or agent. Do not paraphrase the directive — execute it.

| Action tag | Invoke |
|---|---|
| `load-context` | resume-track |
| `record-session` | end-track (which delegates to session-historian) |
| `compact-context` | compact-artifacts |
| `compact-context-aggressive` | compact-artifacts (aggressive mode) |
| `sweep-entropy` | sweep-entropy |
| `collect-feedback` | feedback-collector |
| `run-evaluator` | generate-then-evaluate |
| `verify-output` | verify-output |
| `bootstrap-needed` | bootstrap-project |

Full marker reference: `/home/poc/my_claude_skills/harness-engineering/references/hook-markers.md`

### Artifact Structure

- `docs/active/` — auto-loaded at session start. Hard ceiling 500 lines, soft warn 400.
- `docs/reference/` — never auto-loaded. Search when historical context is needed.

Schema details: `/home/poc/my_claude_skills/harness-engineering/references/track-schema.md`
Budgets: `/home/poc/my_claude_skills/harness-engineering/references/budgets.md`

### Feedback Accumulation

When the user gives directives, corrections, approvals, or preferences, the `collect-feedback` action fires from the UserPromptSubmit hook. Read `references/feedback-patterns.md` for the type taxonomy. Apply relevant feedback to current work before responding.

### Output Verification

After generating visual artifacts (PPTX, PNG, HTML, PDF, SVG, DOCX), the `verify-output` action fires. Never report "file generated" without visual inspection.

### Code Evaluation

After significant code changes (≥10 cumulative changed lines), the `run-evaluator` action fires. Delegate to the evaluator agent for independent review. Fix Critical Issues before declaring completion.
