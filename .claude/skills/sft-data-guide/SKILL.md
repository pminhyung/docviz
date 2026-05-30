---
name: sft-data-guide
description: Surface the EXAONE SFT data-generation rules from exaone/sft_gen/SFT_DATA_GUIDE.md before the agent writes or modifies anything that touches SFT records. Use this skill whenever the user is working on SFT dataset generation, modifying or writing files under exaone/sft_gen/ (build_dataset, query_gen, pa_rag_query_generation, shim/), touching exaone/batch_runner.py / batch_runner_pool.py, modifying exaone/auxiliary_tracer.py (RFD / VLM / web_extract aux log writers feed the SFT pipeline), changing exaone/agent.py system-prompt assembly (system_blocks is part of the record schema), writing dataset filters/validators/preprocessors, adding tests under tests/exaone/ that touch trajectory output, or mentions any of: "SFT 데이터", "학습 데이터", "trajectory", "loss masking", "loss mask", "rollout turn", "history turn", "citation hallucination", "tcid", "aux trajectory", "compaction trajectory", "build_dataset", "query_gen", "batch_runner", "auxiliary tracer", "system_blocks". Trigger even when the user does not name the guide explicitly — the rules in it are silent invariants that quietly break learning if violated.
---

# sft-data-guide

The authoritative spec for EXAONE SFT records — record shape, loss-masking,
tool-call rules, citation rules (`[tcid.idx]`), structural validity, aux-task
trajectories — lives in:

```
exaone/sft_gen/SFT_DATA_GUIDE.md
```

This skill exists so you **stop and Read that file** before producing or
modifying any code that touches SFT records. The file is the single source
of truth; do not copy or paraphrase its rules anywhere else (including into
this skill body), because parts are still TBD (§5 caps, §부록A aux task)
and a paraphrased copy would silently drift.

## What's in the guide (jump-to map)

`§0` schema · `§1` loss masking (1.1 single-turn, 1.2 multi-turn, 1.3 aux) ·
`§2` interleaved thinking · `§3` tool call (3.1 name in tools, 3.2 empty
result, 3.3 args schema, 3.4 distinct tcid) · `§4` citation (4.1
hallucination, 4.2 format) · `§5` length caps · `§6` structural validity ·
`§부록A` aux trajectories.

## When this skill triggers, do this

1. Read `exaone/sft_gen/SFT_DATA_GUIDE.md` — at minimum the sections relevant
   to what you're about to change. The whole file is ~620 lines; full Read
   is fine.
2. Treat every rule there as a hard invariant unless the guide itself flags
   it as TBD/초안.
3. If a tool-result envelope or `auxiliary_*.json` writer you're about to
   change is referenced in the guide, flag the dependency to the user
   instead of unilaterally editing either side — drift between live code
   and this guide is how silent training-data corruption starts.

That's it. The guide does the rest.
