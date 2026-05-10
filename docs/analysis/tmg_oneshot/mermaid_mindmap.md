# `mermaid_mindmap` exemplar pool — revision v1

**Date**: 2026-05-10
**Status**: revision v1 (supersedes the `mermaid_mindmap` portion of
`docs/analysis/tmg_oneshot_pool_draft.md` v0). v0 archived; do **not**
edit it.

**Changes vs v0** (driven by `tmg_oneshot_pool_review.md`):
- **Must-fix #3 + Minor #6 collapsed**: replaced v0's MIND-A (3-level,
  `Daler Mehndi & Tunak Tunak Tun` — prototype-leak risk) with a new
  **2-level shallow** biographical-compare exemplar. New MIND-A is anchored
  on `hotpot_04_comparative` / S4_Agentic (faith 1.00, overall — we use the
  same shape but rewrite to a fully fictional acting-franchise compare so
  no entity overlap with prototype).
- MIND-B unchanged (3-level paper-grouping with Challenge/Solution leaves;
  paper-methods archetype; anchored on `arxiv_01_hierarchical` faith 1.00).
- MIND-C unchanged (4-level matrix-shape; paper-methods archetype; anchored
  on `arxiv_00_comparative` faith 1.00).
- Added consolidated variant (V4_consolidated measurement); see §2.

---

## 1. Pool variant (V4_pool measurement)

3 exemplars covering distinct `mermaid_mindmap` depth profiles:
**2-level** (MIND-A) / **3-level** (MIND-B) / **4-level matrix**
(MIND-C).

### MIND-A — 2-level shallow biographical-compare, Wikipedia archetype (NEW v1)

```json
{"viz_type": "mermaid_mindmap", "viz_dsl": "mindmap\n  root((Cipher Saga<br/>Lead-Cast Comparison))\n    Marielle Vasquez\n      Role: Captain Sera Halvorsen\n      Status: Original Protagonist\n      Timeline: Franchise launched 2009\n      Note: Departed before Cipher Saga III after creative dispute\n    Theo Lindqvist\n      Role: Captain Sera Halvorsen\n      Status: Recast Protagonist\n      Timeline: Cipher Saga III–V (2014–2019)\n      Background: Stage actor (Royal Court Theatre)\n      Significance: Stayed for the trilogy that closed the original arc"}
```

- **Anchor**: `hotpot_04_comparative` / S4_Agentic (faith 1.00, max-indent
  6 — true 2-level). The original entity (`Universal Soldier` / Van Damme /
  Adkins) is **fully replaced** with a fictional franchise to avoid any
  prototype overlap; the anchor structure (root with `<br/>` / 2 sibling
  branches / 4–5 attribute leaves per branch) is preserved exactly.
- **Syntactic feature**: **2-level** — root → 2 sibling branches →
  4–5 leaf attributes per branch. Root uses `<br/>` for multi-line title.
  No deeper nesting.
- **Domain archetype**: Wikipedia-biographical (entertainment-franchise
  compare).
- **Why faith**: shallow comparative source content (e.g., "compare two
  people in the same role") collapses badly when forced into 3+ levels —
  the agent invents intermediate categories that aren't in the source.
  This MIND-A teaches the agent that **2 sibling branches with parallel
  leaf attributes** is the correct shape for shallow biographical compare,
  closing the must-fix #3 (entity-leak) and minor #6 (no shallow
  exemplar) gaps in one swap.

### MIND-B — 3-level paper-grouping with Challenge/Solution leaves, paper-methods archetype

```json
{"viz_type": "mermaid_mindmap", "viz_dsl": "mindmap\n  root((Three Recent Papers by Core ML Challenge))\n    Distribution Shift Under Sparse Labels\n      Adaptive Pseudo-Labeling for Streaming Sensor Data\n        Challenge: Concept drift in unlabeled sensor streams\n        Solution: Confidence-thresholded pseudo-label injection with EMA teacher\n    Long-Tail Multi-Modal Retrieval\n      Cross-Modal Contrastive Tail Boosting\n        Challenge: Tail-class collapse in joint vision-language embedding space\n        Solution: Per-class temperature scaling with hard-negative mining from text neighbours\n    Causal Stability of Foundation Models\n      Counterfactual Probe Suite for Pretrained Encoders\n        Challenge: Spurious feature reliance under covariate shift\n        Solution: Causal probing toolkit with intervention sets and stability index"}
```

- **Anchor**: `arxiv_01_hierarchical` / S1_Direct (faith 1.00, overall 1.00);
  paraphrased to fictional papers in different ML areas.
- **Syntactic feature**: **3-level** — root → 3 thematic groups → 1 paper
  title per group → Challenge/Solution sub-leaves. Paper titles as full
  noun phrases. Parallel Challenge/Solution structure across groups.
- **Domain archetype**: paper-methods.
- **Why faith**: anchors the agent on the **paper-grouping-by-theme** shape
  with explicit Challenge/Solution sub-leaves — the high-faith pattern for
  arxiv hierarchical that the placeholder's flat NLP-methods example
  cannot teach.

### MIND-C — 4-level matrix-shape (compare 2 methods × parallel axes), paper-methods archetype

```json
{"viz_type": "mermaid_mindmap", "viz_dsl": "mindmap\n  root((Parameter Update Mechanisms<br/>(Two Recent RL Methods)))\n    In-Context Adapter Tuning\n      Optimization Target\n        Cross-entropy on next-token prediction\n        Self-supervised, no reward model\n      Updated Weights\n        Lightweight adapter layers only (~0.4% of params)\n        Frozen backbone for compute efficiency\n      Update Procedure\n        Single forward-backward per chunk of 512 tokens\n        Update Rule\n          theta_adapter <- theta_adapter - eta * grad_L_NTP\n          eta scheduled with cosine decay\n      Distinctive Property\n        No architectural changes to the base model\n        Drop-in replacement for full fine-tuning\n    Distributional Policy Alignment\n      Optimization Target\n        Reverse-KL between policy and target distribution q\n        Reward-weighted, derived from preference scores\n      Target Distribution\n        q_i proportional to p_old_i * exp(u_i / tau)\n        u_i: standardized preference scores\n      Update Procedure\n        Cross-entropy fitting to q over batches of 8 candidates\n        Gradient on Policy Logits\n          dL/dl_i = p_theta_i - q_i\n      Distinctive Property\n        Decouples target construction from policy fitting\n        Gradient vanishes once policy matches target q"}
```

- **Anchor**: `arxiv_00_comparative` / S4_Agentic (faith 1.00, overall 1.00);
  paraphrased to fictional RL methods.
- **Syntactic feature**: **4-level matrix shape** — root → 2 method
  branches → 4 parallel axes per method → leaf details. Embedded **multi-
  line `<br/>`** in the root, **inline math** as text leaves
  (`theta_adapter <- ... - eta * grad_L_NTP`).
- **Domain archetype**: paper-methods.
- **Why faith**: exact content style of the post-mortem D1 winner. Without
  this matrix shape, the agent collapses 2-method × N-axis comparisons to
  either a flat 3-branch mindmap (loses axis parallelism) or a 4-bar
  chartjs (loses axis-name grounding entirely).

---

## 2. Consolidated variant (V4_consolidated measurement)

A single integrated `mermaid_mindmap` that, **inside one coherent
mindmap rooted at one root node**, exhibits:

- a **2-level shallow** branch (sibling with leaf attributes only)
- a **3-level** branch (sibling → child → grand-child leaf list)
- a **4-level matrix** branch (sibling → 2 sub-branches → parallel axes →
  leaf details)
- multi-line `<br/>` in the root
- a mix of plain-text leaves and **inline-math leaves**

The integration is achieved by using **one consistent domain root** (a
single research project's organisational mindmap, with deliberate
asymmetry — the project's "team" branch is shallow, its "milestones"
branch is medium-depth, its "methods" branch is the deep matrix).

```json
{"viz_type": "mermaid_mindmap", "viz_dsl": "mindmap\n  root((Foundry Research Institute<br/>Alignment Programme — 2024 Snapshot))\n    Team\n      Lead: Dr. Naomi Castellan\n      Headcount: 12 researchers and 3 engineers\n      Funding: Mixed government and philanthropic grants\n    Milestones\n      2022 Q3 Pilot Release\n        Open-sourced csc-eval calibration toolkit\n        Adopted by three external academic groups within six months\n      2023 NeurIPS Best Paper\n        Calibrated Self-Critique\n        Cited 480+ times by end of 2024\n      2024 Public Audit Programme\n        Quarterly third-party model cards published\n        Independent reviewer panel rotated yearly\n    Methods\n      Calibrated Self-Critique\n        Optimization Target\n          Cross-entropy on critique-vs-base preference pairs\n          Auxiliary calibration loss on confidence bins\n        Updated Weights\n          Critic head only (~1.2% of base model params)\n          Base model frozen during critique training\n        Update Rule\n          theta_critic <- theta_critic - eta * grad_L_calib\n          L_calib = CE_pref + lambda * ECE_bin\n      Refusal-Aware Reward Modelling\n        Optimization Target\n          Pairwise reward with explicit refusal class\n          KL anchor to safety-tuned reference policy\n        Updated Weights\n          Full reward head and bottom 4 transformer blocks\n          Anchor model frozen for KL computation\n        Update Rule\n          theta_rm <- theta_rm - eta * grad_L_pref\n          plus beta * KL(pi_theta || pi_ref)"}
```

- **Source**: hand-written; content style anchored on MIND-A (2-level
  sibling-with-leaves), MIND-B (3-level grouping), and MIND-C (4-level
  matrix with inline math).
- **Domain archetype**: research-organisation provenance (a single
  research programme described from three angles at three depths).
- **Integrated patterns**:
  - shallow 2-level branch: `Team` → 3 attribute leaves
  - medium 3-level branch: `Milestones` → 3 milestones → 2 sub-leaves each
  - deep 4-level matrix branch: `Methods` → 2 methods → 3 axes per method
    → leaf details (with **inline-math leaves**)
  - root has `<br/>` multi-line title
  - parallel structure inside the matrix branch (Optimization Target /
    Updated Weights / Update Rule axes mirrored across 2 methods)
- **Length budget**: 1610 chars ≈ ~410 tokens. (Mindmap is the largest
  consolidated of the 6 types because the depth-mixing is the whole
  point — a shorter version cannot demonstrate the 2-vs-3-vs-4 spread.)
- **Intent**: V4_consolidated independent measurement.

---

## 3. Python literal — drop-in for `tmg.py`

### 3.1 Pool literal

```python
ONE_SHOT_POOL_BY_VIZ_TYPE["mermaid_mindmap"] = [
    # MIND-A — 2-level shallow biographical-compare, Wikipedia archetype (NEW v1, anchored on hotpot_04_comparative shape, fully fictional entities)
    '{"viz_type": "mermaid_mindmap", "viz_dsl": "mindmap\\n  root((Cipher Saga<br/>Lead-Cast Comparison))\\n    Marielle Vasquez\\n      Role: Captain Sera Halvorsen\\n      Status: Original Protagonist\\n      Timeline: Franchise launched 2009\\n      Note: Departed before Cipher Saga III after creative dispute\\n    Theo Lindqvist\\n      Role: Captain Sera Halvorsen\\n      Status: Recast Protagonist\\n      Timeline: Cipher Saga III\\u2013V (2014\\u20132019)\\n      Background: Stage actor (Royal Court Theatre)\\n      Significance: Stayed for the trilogy that closed the original arc"}',
    # MIND-B — 3-level with challenge/solution leaves, paper-methods archetype
    '{"viz_type": "mermaid_mindmap", "viz_dsl": "mindmap\\n  root((Three Recent Papers by Core ML Challenge))\\n    Distribution Shift Under Sparse Labels\\n      Adaptive Pseudo-Labeling for Streaming Sensor Data\\n        Challenge: Concept drift in unlabeled sensor streams\\n        Solution: Confidence-thresholded pseudo-label injection with EMA teacher\\n    Long-Tail Multi-Modal Retrieval\\n      Cross-Modal Contrastive Tail Boosting\\n        Challenge: Tail-class collapse in joint vision-language embedding space\\n        Solution: Per-class temperature scaling with hard-negative mining from text neighbours\\n    Causal Stability of Foundation Models\\n      Counterfactual Probe Suite for Pretrained Encoders\\n        Challenge: Spurious feature reliance under covariate shift\\n        Solution: Causal probing toolkit with intervention sets and stability index"}',
    # MIND-C — 4-level matrix-shape (compare 2 methods × parallel axes), paper-methods archetype
    '{"viz_type": "mermaid_mindmap", "viz_dsl": "mindmap\\n  root((Parameter Update Mechanisms<br/>(Two Recent RL Methods)))\\n    In-Context Adapter Tuning\\n      Optimization Target\\n        Cross-entropy on next-token prediction\\n        Self-supervised, no reward model\\n      Updated Weights\\n        Lightweight adapter layers only (~0.4% of params)\\n        Frozen backbone for compute efficiency\\n      Update Procedure\\n        Single forward-backward per chunk of 512 tokens\\n        Update Rule\\n          theta_adapter <- theta_adapter - eta * grad_L_NTP\\n          eta scheduled with cosine decay\\n      Distinctive Property\\n        No architectural changes to the base model\\n        Drop-in replacement for full fine-tuning\\n    Distributional Policy Alignment\\n      Optimization Target\\n        Reverse-KL between policy and target distribution q\\n        Reward-weighted, derived from preference scores\\n      Target Distribution\\n        q_i proportional to p_old_i * exp(u_i / tau)\\n        u_i: standardized preference scores\\n      Update Procedure\\n        Cross-entropy fitting to q over batches of 8 candidates\\n        Gradient on Policy Logits\\n          dL/dl_i = p_theta_i - q_i\\n      Distinctive Property\\n        Decouples target construction from policy fitting\\n        Gradient vanishes once policy matches target q"}',
]
```

### 3.2 Consolidated literal

```python
ONE_SHOT_CONSOLIDATED_BY_VIZ_TYPE["mermaid_mindmap"] = (
    '{"viz_type": "mermaid_mindmap", "viz_dsl": "mindmap\\n  root((Foundry Research Institute<br/>Alignment Programme \\u2014 2024 Snapshot))\\n    Team\\n      Lead: Dr. Naomi Castellan\\n      Headcount: 12 researchers and 3 engineers\\n      Funding: Mixed government and philanthropic grants\\n    Milestones\\n      2022 Q3 Pilot Release\\n        Open-sourced csc-eval calibration toolkit\\n        Adopted by three external academic groups within six months\\n      2023 NeurIPS Best Paper\\n        Calibrated Self-Critique\\n        Cited 480+ times by end of 2024\\n      2024 Public Audit Programme\\n        Quarterly third-party model cards published\\n        Independent reviewer panel rotated yearly\\n    Methods\\n      Calibrated Self-Critique\\n        Optimization Target\\n          Cross-entropy on critique-vs-base preference pairs\\n          Auxiliary calibration loss on confidence bins\\n        Updated Weights\\n          Critic head only (~1.2% of base model params)\\n          Base model frozen during critique training\\n        Update Rule\\n          theta_critic <- theta_critic - eta * grad_L_calib\\n          L_calib = CE_pref + lambda * ECE_bin\\n      Refusal-Aware Reward Modelling\\n        Optimization Target\\n          Pairwise reward with explicit refusal class\\n          KL anchor to safety-tuned reference policy\\n        Updated Weights\\n          Full reward head and bottom 4 transformer blocks\\n          Anchor model frozen for KL computation\\n        Update Rule\\n          theta_rm <- theta_rm - eta * grad_L_pref\\n          plus beta * KL(pi_theta || pi_ref)"}'
)
```

---

## 4. 검수 체크리스트

- [x] **Syntactic spread of 3 pool exemplars**:
  - MIND-A: 2-level / 1 root → 2 siblings → 4-5 leaves each (NEW v1)
  - MIND-B: 3-level / 1 root → 3 thematic groups → 1 paper → 2 sub-leaves
  - MIND-C: 4-level matrix / 1 root → 2 methods → 4 axes → leaf details
  → covers (depth 2 vs 3 vs 4) × (single-branch leaves vs grouped vs
  matrix) × (with `<br/>` root vs plain root) × (Wikipedia vs paper-
  methods archetypes).
- [x] **Anchor authenticity**: MIND-A anchored on `hotpot_04_comparative`
  S4_Agentic (faith 1.00) shape, entities fully fictional; MIND-B and
  MIND-C anchored on real records (faith 1.00 each). Must-fix #3 closed:
  no `Daler Mehndi & Tunak Tunak Tun` or any other prototype-overlap entity.
- [x] **Placeholder regression check**: no `NLP Methods / Supervised /
  Self-supervised / RL-based` flat 3-layer toy structure; no single-word
  abstract category leaves. All entities fictional generic-domain.
- [x] **Consolidated variant integration**: a single coherent mindmap with
  one root and three branches at three depths (Team = 2-level, Milestones
  = 3-level, Methods = 4-level matrix with inline math). Branches share
  the same domain (one research programme described from three angles).
- [x] **JSON round-trip**: all 4 strings parse via `json.loads`; `viz_type
  == "mermaid_mindmap"` for all; `viz_dsl` value starts with `mindmap\n`.
- [x] **Token budget for consolidated**: ~1610 chars ≈ ~410 tokens. Largest
  of the 6 consolidated examples — justified because mindmap depth-mixing
  cannot be demonstrated in fewer levels.
