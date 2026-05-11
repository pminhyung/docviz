# `mermaid_flowchart` exemplar pool — revision v1

**Date**: 2026-05-10
**Status**: revision v1 (supersedes the `mermaid_flowchart` portion of
`docs/analysis/tmg_oneshot_pool_draft.md` v0). v0 archived; do **not**
edit it.

**Changes vs v0** (driven by `tmg_oneshot_pool_review.md`):
- FLOW-A unchanged (5-node chain LR with descriptive role-edges; Wikipedia
  archetype; anchored on `hotpot_00_relational` faith 1.00).
- **Must-fix #2**: replaced v0's FLOW-B (intent-vs-impact subgraph,
  `multinews_05_comparative` anchor, ~30 nodes, +800 token cost) with a
  **pure hub-and-spoke** exemplar (paper-methods archetype, hand-written).
  Rationale: v0 already covered the "subgraph cluster" shape via FLOW-C
  (parallel-subgraphs); the hub-and-spoke shape was missing entirely;
  also reduces FLOW-B's token cost (review minor #3).
- FLOW-C unchanged (2 parallel subgraphs; paper-methods archetype; anchored
  on `arxiv_00_comparative` faith 1.00).
- Added consolidated variant (V4_consolidated measurement); see §2.

---

## 1. Pool variant (V4_pool measurement)

3 exemplars covering the three canonical `mermaid_flowchart` shapes:
**chain** (FLOW-A) / **hub-and-spoke** (FLOW-B) / **subgraph cluster**
(FLOW-C).

### FLOW-A — 5-node chain LR with descriptive role-edges, Wikipedia archetype

```json
{"viz_type": "mermaid_flowchart", "viz_dsl": "graph LR\n    A[Vice-Admiral Ravindra Sethi] -->|Retired Indian Navy Flag Officer| B(Western Naval Command)\n    B -->|Authorized Operation Trident-II in| C[December 1971]\n    C -->|Launched missile-boat strike against| D[Karachi Harbour Oil Depot]\n    D -->|Located in| E[Karachi, Sindh, Pakistan]"}
```

- **Anchor**: `hotpot_00_relational` / S4_Agentic (faith 1.00, overall 0.92);
  rewritten as a fictional naval engagement to avoid prototype lift.
- **Syntactic feature**: 5-node chain / **left-to-right** orientation /
  edge labels are **role-descriptive phrases** (not single verbs).
- **Domain archetype**: Wikipedia-historical / news.
- **Why faith**: replaces the failing `A -->|founded| B -->|acquired| C
  -->|hired| D` pattern with the high-faith *actual* style — entity names
  with appositive titles, edges as full role descriptions, intermediate
  dates/places as named nodes. Counters C5 (a)(d)(e) flattening directly.

### FLOW-B — pure hub-and-spoke, 1 center + 6 peripherals, paper-methods archetype (NEW v1)

```json
{"viz_type": "mermaid_flowchart", "viz_dsl": "graph TD\n    H[Direct Preference Optimization<br/>Loss Function]\n    H -->|Replaces| P1[KL-Penalized RLHF Reward Loop]\n    H -->|Operates on| P2[Pairs of Chosen vs Rejected Completions]\n    H -->|Reparameterizes Reward as| P3[Implicit Reward = beta * log<br/>policy ratio over reference]\n    H -->|Optimizes via| P4[Standard Cross-Entropy on Preference Pairs]\n    H -->|Avoids Need for| P5[Separate Reward Model Training]\n    H -->|Reported to Match or Exceed| P6[PPO-Based RLHF on Helpful-Harmless Benchmarks]"}
```

- **Source**: hand-written (no real anchor in the prototype pool exhibits a
  pure hub-and-spoke without subgraph clustering; the closest, `hotpot_07_
  relational` S1_Direct faith 1.00, is a chain-with-fan, not a pure hub).
  Content style anchored on `arxiv_00_comparative` and FLOW-A's role-
  descriptive edge convention.
- **Syntactic feature**: 1 center node (the **hub**, declared on its own
  line) with 6 outgoing edges to **named peripheral nodes** / top-down
  orientation / **`<br/>` multi-line text** inside hub and one peripheral
  / role-descriptive edge labels (`"Replaces"`, `"Operates on"`,
  `"Reparameterizes Reward as"`, `"Reported to Match or Exceed"`).
- **Domain archetype**: paper-methods (Mermaid-side paper-methods coverage
  was previously light; this rebalances).
- **Why faith**: gives the agent a clean **central concept + N attributes**
  template that paper-methods queries (and Wikipedia-of-a-single-concept
  queries) need. Without this, the agent collapses concept-with-attributes
  source content to either a chain (loses the parallelism) or a 2-subgraph
  shape (over-clusters when no clustering is warranted).

### FLOW-C — 2 parallel labelled subgraphs, paper-methods archetype

```json
{"viz_type": "mermaid_flowchart", "viz_dsl": "graph TD\n    subgraph Method_A [\"Latent Diffusion with Cross-Attention Conditioning\"]\n        direction TB\n        A1[Input: Text Prompt + Reference Image] --> B1[CLIP Text Encoder]\n        B1 --> C1[Cross-Attention Block in U-Net]\n        C1 --> D1[Iterative Denoising over 50 Steps]\n        D1 --> E1[Output: 512x512 Synthesized Image]\n    end\n\n    subgraph Method_B [\"Flow-Matching with Direct Conditioning\"]\n        direction TB\n        A2[Input: Text Prompt + Reference Image] --> B2[T5-XL Text Encoder]\n        B2 --> C2[Concatenated Conditioning at Block Input]\n        C2 --> D2[Single-Step ODE Integration]\n        D2 --> E2[Output: 1024x1024 Synthesized Image]\n    end\n\n    style Method_A fill:#e1f5fe,stroke:#01579b,stroke-width:2px\n    style Method_B fill:#f3e5f5,stroke:#4a148c,stroke-width:2px\n    style C1 fill:#bbdefb,stroke:#01579b\n    style C2 fill:#e1bee7,stroke:#4a148c"}
```

- **Anchor**: `arxiv_00_comparative` / S1_Direct (faith 1.00, overall 0.89);
  paraphrased to a fictional image-synthesis comparison.
- **Syntactic feature**: **two parallel subgraphs** with internal direction
  (`direction TB`) / mirrored 5-stage pipelines / color coding via `style`.
- **Domain archetype**: paper-methods.
- **Why faith**: exact content style of the post-mortem D1 winner. The
  failing placeholder cannot represent two parallel pipelines with
  mirrored stages — the paper-methods comparative shape.

---

## 2. Consolidated variant (V4_consolidated measurement)

A single integrated `mermaid_flowchart` that, **inside one coherent
graph**, exhibits:

- a **chain section** (sequential `-->` with role-descriptive edge labels)
- a **hub-and-spoke section** (one center fanning out to 4 peripherals)
- a **subgraph-cluster section** (1 named `subgraph` containing 3 internal
  nodes with their own internal `direction`)

The integration is achieved by using **one consistent domain** (research-
paper provenance: an author's research line, the central paper as hub, and
a subgraph for follow-up work) so that the whole graph reads as a single
coherent diagram rather than three stitched fragments.

```json
{"viz_type": "mermaid_flowchart", "viz_dsl": "graph TD\n    %% chain section: career trajectory\n    A[Dr. Naomi Castellan<br/>PhD, Cambridge, 2014] -->|Postdoc 2014–2017 at| B[Stanford NLP Group]\n    B -->|Joined as Senior Research Scientist in 2017| C[Foundry Research Institute]\n    C -->|Promoted in 2021 to lead the| D[Alignment & Evaluation Team]\n\n    %% hub-and-spoke section: the team's flagship contribution\n    D -->|Co-led publication of| H[Calibrated Self-Critique<br/>NeurIPS 2023 Best Paper]\n    H -->|Introduced metric| P1[Self-Critique Calibration Index]\n    H -->|Reframed evaluation as| P2[Two-Step Generation-then-Refutation]\n    H -->|Demonstrated SOTA on| P3[TruthfulQA and HaluEval-Hard]\n    H -->|Released open implementation as| P4[csc-eval Python Package]\n\n    %% subgraph-cluster section: follow-up ecosystem\n    subgraph Followup [\"Follow-Up Work Citing Castellan et al. (2023)\"]\n        direction LR\n        F1[Iterative Self-Critique with RLHF Reward<br/>(2024)] --> F2[Multi-Agent Critique Ensembles<br/>(2024)]\n        F2 --> F3[Domain-Specialised Critics for Clinical NLP<br/>(2025)]\n    end\n\n    H -->|Cited by| F1\n\n    style H fill:#fff3e0,stroke:#e65100,stroke-width:2px\n    style Followup fill:#e8f5e9,stroke:#1b5e20,stroke-width:1px"}
```

- **Source**: hand-written; content style anchored on FLOW-A (chain with
  role-descriptive edges), FLOW-B (hub-and-spoke), and `arxiv_00_
  comparative` (subgraph-with-`direction LR`).
- **Domain archetype**: paper-methods / academic-provenance (single
  coherent biographical research-line domain).
- **Integrated patterns**:
  - chain section: A → B → C → D with full role-descriptive edge labels
  - hub-and-spoke section: D → H, then H → {P1, P2, P3, P4}
  - subgraph-cluster section: a named `subgraph Followup` with internal
    `direction LR` and 3 sequenced nodes
  - cross-section connection: H → F1 (the subgraph and the hub are wired
    into the same graph)
  - `style` coloring on hub (H) and subgraph (Followup)
  - `<br/>` multi-line labels (with paper-year tags) inside several nodes
  - `%%` comments used as section dividers (Mermaid-legal)
- **Length budget**: 1320 chars ≈ ~340 tokens.
- **Intent**: V4_consolidated independent measurement. The agent sees one
  example demonstrating that a single flowchart can carry chain + hub +
  subgraph patterns simultaneously when source content has a coherent
  through-line.

---

## 3. Python literal — drop-in for `tmg.py`

### 3.1 Pool literal

```python
ONE_SHOT_POOL_BY_VIZ_TYPE["mermaid_flowchart"] = [
    # FLOW-A — 5-node chain LR with descriptive role-edges, Wikipedia archetype
    '{"viz_type": "mermaid_flowchart", "viz_dsl": "graph LR\\n    A[Vice-Admiral Ravindra Sethi] -->|Retired Indian Navy Flag Officer| B(Western Naval Command)\\n    B -->|Authorized Operation Trident-II in| C[December 1971]\\n    C -->|Launched missile-boat strike against| D[Karachi Harbour Oil Depot]\\n    D -->|Located in| E[Karachi, Sindh, Pakistan]"}',
    # FLOW-B — pure hub-and-spoke (1 center + 6 peripherals), paper-methods archetype (NEW v1, hand-written)
    '{"viz_type": "mermaid_flowchart", "viz_dsl": "graph TD\\n    H[Direct Preference Optimization<br/>Loss Function]\\n    H -->|Replaces| P1[KL-Penalized RLHF Reward Loop]\\n    H -->|Operates on| P2[Pairs of Chosen vs Rejected Completions]\\n    H -->|Reparameterizes Reward as| P3[Implicit Reward = beta * log<br/>policy ratio over reference]\\n    H -->|Optimizes via| P4[Standard Cross-Entropy on Preference Pairs]\\n    H -->|Avoids Need for| P5[Separate Reward Model Training]\\n    H -->|Reported to Match or Exceed| P6[PPO-Based RLHF on Helpful-Harmless Benchmarks]"}',
    # FLOW-C — 2 parallel labelled subgraphs (compare two pipelines), paper-methods archetype
    '{"viz_type": "mermaid_flowchart", "viz_dsl": "graph TD\\n    subgraph Method_A [\\"Latent Diffusion with Cross-Attention Conditioning\\"]\\n        direction TB\\n        A1[Input: Text Prompt + Reference Image] --> B1[CLIP Text Encoder]\\n        B1 --> C1[Cross-Attention Block in U-Net]\\n        C1 --> D1[Iterative Denoising over 50 Steps]\\n        D1 --> E1[Output: 512x512 Synthesized Image]\\n    end\\n\\n    subgraph Method_B [\\"Flow-Matching with Direct Conditioning\\"]\\n        direction TB\\n        A2[Input: Text Prompt + Reference Image] --> B2[T5-XL Text Encoder]\\n        B2 --> C2[Concatenated Conditioning at Block Input]\\n        C2 --> D2[Single-Step ODE Integration]\\n        D2 --> E2[Output: 1024x1024 Synthesized Image]\\n    end\\n\\n    style Method_A fill:#e1f5fe,stroke:#01579b,stroke-width:2px\\n    style Method_B fill:#f3e5f5,stroke:#4a148c,stroke-width:2px\\n    style C1 fill:#bbdefb,stroke:#01579b\\n    style C2 fill:#e1bee7,stroke:#4a148c"}',
]
```

### 3.2 Consolidated literal

```python
ONE_SHOT_CONSOLIDATED_BY_VIZ_TYPE["mermaid_flowchart"] = (
    '{"viz_type": "mermaid_flowchart", "viz_dsl": "graph TD\\n    %% chain section: career trajectory\\n    A[Dr. Naomi Castellan<br/>PhD, Cambridge, 2014] -->|Postdoc 2014\\u20132017 at| B[Stanford NLP Group]\\n    B -->|Joined as Senior Research Scientist in 2017| C[Foundry Research Institute]\\n    C -->|Promoted in 2021 to lead the| D[Alignment & Evaluation Team]\\n\\n    %% hub-and-spoke section: the team\'s flagship contribution\\n    D -->|Co-led publication of| H[Calibrated Self-Critique<br/>NeurIPS 2023 Best Paper]\\n    H -->|Introduced metric| P1[Self-Critique Calibration Index]\\n    H -->|Reframed evaluation as| P2[Two-Step Generation-then-Refutation]\\n    H -->|Demonstrated SOTA on| P3[TruthfulQA and HaluEval-Hard]\\n    H -->|Released open implementation as| P4[csc-eval Python Package]\\n\\n    %% subgraph-cluster section: follow-up ecosystem\\n    subgraph Followup [\\"Follow-Up Work Citing Castellan et al. (2023)\\"]\\n        direction LR\\n        F1[Iterative Self-Critique with RLHF Reward<br/>(2024)] --> F2[Multi-Agent Critique Ensembles<br/>(2024)]\\n        F2 --> F3[Domain-Specialised Critics for Clinical NLP<br/>(2025)]\\n    end\\n\\n    H -->|Cited by| F1\\n\\n    style H fill:#fff3e0,stroke:#e65100,stroke-width:2px\\n    style Followup fill:#e8f5e9,stroke:#1b5e20,stroke-width:1px"}'
)
```

> **Note on Python literal escapes**: the `–` en-dash inside the consolidated
> string is escaped as `…` style `–` to keep the Python source
> file ASCII-clean if `tmg.py` enforces ASCII; remove the escape if the
> file declares `# -*- coding: utf-8 -*-` or is Python 3 (default UTF-8).
> The `\\n` inside `<br/>` etc. are Mermaid line-break tags; the outer `\\n`
> are JSON-string newlines that the agent reads as actual newlines.

---

## 4. 검수 체크리스트

- [x] **Syntactic spread of 3 pool exemplars**:
  - FLOW-A: chain / 5 nodes / LR / role-descriptive edge labels
  - FLOW-B: hub-and-spoke / 1 hub + 6 peripherals / TD / no subgraph
  - FLOW-C: 2 parallel subgraphs / TD with internal `direction TB` /
    mirrored 5-stage pipelines / styled
  → all three canonical flowchart shapes covered (must-fix #2 closed).
- [x] **Anchor authenticity**: FLOW-A and FLOW-C anchored (faith 1.00 each);
  FLOW-B hand-written and **explicitly disclosed** (no real prototype anchor
  exhibits pure hub-and-spoke; the closest, `hotpot_07_relational` S1_Direct,
  is chain-with-fan).
- [x] **Placeholder regression check**: no `Acme Corp / Founder / Engineer X`
  anywhere; no `founded / acquired / hired` single-verb edges. Edge labels
  are full role descriptions (`"Retired Indian Navy Flag Officer"`,
  `"Reparameterizes Reward as"`, `"Promoted in 2021 to lead the"`).
- [x] **Consolidated variant integration**: a single coherent graph that
  contains a chain section + hub-and-spoke section + subgraph-cluster
  section, all wired into one connected component via `D → H` and
  `H → F1`. Domain through-line is one researcher's career provenance.
- [x] **JSON round-trip**: all 4 strings parse via `json.loads`; `viz_type ==
  "mermaid_flowchart"` for all; `viz_dsl` value starts with the Mermaid
  header `graph TD` or `graph LR` (header sniff passes).
- [x] **Token budget for consolidated**: ~1320 chars ≈ ~340 tokens. The v0
  FLOW-B (~1300 chars in DSL alone, +800 prompt tokens vs placeholder) is
  removed; the new pool's FLOW-B is ~700 chars, so the consolidated cost is
  recovered.
