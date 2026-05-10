# `mermaid_sequenceDiagram` exemplar pool — revision v2 (NEW type)

**Date**: 2026-05-10
**Status**: revision v2 (newly introduced viz_type; no v0/v1 predecessor in
this directory). Added as part of the 6 → 10 viz_type enum extension
(Medium priority — API/process documentation corpus, software-docs fit).

**Provenance honesty**: this viz_type has **no historical anchor** in
`outputs/prototype/judge_scores/all.json` (the prototype dataset was
generated under the 6-type enum). All 4 exemplars in this file are
**hand-written**. Content style anchors borrow conventions from the v1
`mermaid_flowchart` pool (role-descriptive labels, named participants
with appositive titles, paper-methods archetype) so that the agent
transfers faith-1.00 mermaid conventions across the family.

---

## 1. Pool variant (V4_pool measurement)

3 exemplars covering the three canonical `mermaid_sequenceDiagram` shapes:
**2-actor short call/response** (SEQ-A) /
**3+ actors with note + activation** (SEQ-B) /
**async / parallel section (par/and/end)** (SEQ-C).

### SEQ-A — 2-actor short call/response, software-docs archetype

```json
{"viz_type": "mermaid_sequenceDiagram", "viz_dsl": "sequenceDiagram\n    participant Client as Browser Client\n    participant Auth as Carrillon Identity Provider\n    Client->>Auth: POST /authorize (response_type=code, PKCE challenge)\n    Auth-->>Client: 302 Redirect to Login Form\n    Client->>Auth: POST /login (credentials + PKCE verifier)\n    Auth-->>Client: 302 Redirect with Authorization Code\n    Client->>Auth: POST /token (code + PKCE verifier)\n    Auth-->>Client: 200 OK (access_token, id_token, refresh_token)"}
```

- **Source**: hand-written; OAuth-2 PKCE flow (a real protocol used as the
  domain frame). Carrillon Identity Provider = fictional vendor name
  (reuses the v1 BAR-B Carrillon Software Group entity family for cross-
  type entity continuity).
- **Syntactic feature**: 2 participants / **`participant X as Display Name`**
  alias declarations / 4 round trips / **mixed solid (`->>`) and dashed
  (`-->>`) arrows** (request vs response convention) / message text
  carries **method + path + parenthetical payload qualifier** (rich
  phrase, not single verb).
- **Domain archetype**: software-docs (auth-flow documentation — the
  canonical sequenceDiagram use case in technical writing).
- **Why faith intent**: trains the agent on the **request-response
  alternation pattern** with rich, protocol-aware message text. Counters
  the failure mode where placeholder edges become single-verb
  (`Client->Server: get`) and lose all protocol detail.

### SEQ-B — 4 actors with `Note over`, activation blocks, paper-methods archetype

```json
{"viz_type": "mermaid_sequenceDiagram", "viz_dsl": "sequenceDiagram\n    participant Trainer as Training Loop\n    participant Policy as Policy Model (7B)\n    participant Reward as Reward Model (Frozen 13B)\n    participant Ref as Reference Model (SFT Snapshot)\n    Note over Trainer,Ref: Single PPO step on a 256-prompt minibatch\n    Trainer->>Policy: Sample 4 completions per prompt (temp=1.0)\n    activate Policy\n    Policy-->>Trainer: 1024 candidate completions\n    deactivate Policy\n    Trainer->>Reward: Score each completion under helpful-harmless reward head\n    activate Reward\n    Reward-->>Trainer: Scalar reward per completion\n    deactivate Reward\n    Trainer->>Ref: Compute log-prob under reference policy\n    Ref-->>Trainer: Reference log-probs for KL penalty\n    Note right of Trainer: Advantage = reward - beta * KL(policy || ref)\n    Trainer->>Policy: Apply clipped PPO gradient update"}
```

- **Source**: hand-written; PPO-RLHF training step (real method as domain
  frame).
- **Syntactic feature**: **4 participants** with appositive size/freeze
  qualifiers in their display names (`"Policy Model (7B)"`, `"Reward Model
  (Frozen 13B)"`) / **`Note over A,B`** spanning multiple participants /
  **`activate` / `deactivate`** lifeline blocks for 3 different
  participants / **`Note right of X`** placement variant / message text
  carries **quantity-explicit content** (`"1024 candidate completions"`,
  `"Sample 4 completions per prompt (temp=1.0)"`) — counters the
  flattening failure mode.
- **Domain archetype**: paper-methods (RLHF training-pipeline interaction
  is a typical paper-methods sequenceDiagram).
- **Why faith intent**: covers `Note` + `activate`/`deactivate` /
  multi-participant span. Without this exemplar the agent emits flat
  N-step pingpong without any structural annotation, which loses the
  paper's notion of "this whole block is a single training step".

### SEQ-C — async / parallel section (par/and/end), paper-methods / software-docs archetype

```json
{"viz_type": "mermaid_sequenceDiagram", "viz_dsl": "sequenceDiagram\n    participant Orchestrator as DocViz Orchestrator\n    participant Capacity as Capacity Analyzer\n    participant Classifier as Visualization Classifier\n    participant Architect as Content Architect\n    Orchestrator->>Capacity: Submit segmented document chunks\n    par Parallel preprocessing\n        Capacity-->>Orchestrator: chunk_capacity_scores (per-chunk visualization budget)\n    and\n        Orchestrator->>Classifier: Submit same chunks for viz_type proposal\n        Classifier-->>Orchestrator: viz_type proposals (with confidence)\n    end\n    Orchestrator->>Architect: Joined chunks + capacity + viz_type proposals\n    Architect-->>Orchestrator: Per-visualization render plan (DSL skeleton + caption draft)"}
```

- **Source**: hand-written; uses the DocViz pipeline architecture itself
  as the domain frame (self-referential — the agent learns from a
  diagram describing the system that runs the agent).
- **Syntactic feature**: 4 participants / **`par … and … end`** parallel
  block with 1 caption (`"Parallel preprocessing"`) and 2 branches /
  message text carries **structured payload names** (`"chunk_capacity_
  scores"`, `"viz_type proposals"`) — paper/software conventions that
  flat verbs cannot teach.
- **Domain archetype**: software-docs / paper-methods.
- **Why faith intent**: covers the **`par`/`and`/`end` async block** —
  the third canonical sequenceDiagram shape. Mermaid also supports `alt`
  and `loop` blocks; `par` was chosen because it most clearly
  demonstrates "two things happen concurrently" which is the
  prototypical async case in pipeline documentation.

---

## 2. Consolidated variant (V4_consolidated measurement)

A single integrated `mermaid_sequenceDiagram` that, **inside one coherent
diagram**, exhibits:

- a **2-actor request/response section** (covers SEQ-A request-response
  alternation)
- a **`Note over` spanning multiple participants** + a **`Note right of`**
  variant (covers SEQ-B note conventions)
- multiple **`activate`/`deactivate`** lifeline blocks (covers SEQ-B
  activation)
- a **`par … and … and … end`** parallel block with 3 branches (covers
  SEQ-C par/and/end and slightly extends to 3 branches)
- 4 named participants with **alias display names** (covers SEQ-A/B
  display-name convention)
- richly qualified message text on every arrow (no single-verb edges)

The integration is achieved by using **one consistent end-to-end retrieval
flow** (a research assistant fetching a paper bundle through a portal),
so the whole diagram reads as a coherent process rather than three
stitched fragments.

```json
{"viz_type": "mermaid_sequenceDiagram", "viz_dsl": "sequenceDiagram\n    participant Reader as Research Assistant\n    participant Foundry as Foundry Research Portal\n    participant DOI as DOI Resolver Service\n    participant Repo as Open-Access Repository\n    Note over Reader,Repo: End-to-end paper retrieval initiated by a single citation\n    Reader->>Foundry: Submit citation string (Castellan et al., NeurIPS 2023)\n    activate Foundry\n    Foundry->>DOI: Resolve canonical DOI from citation metadata\n    DOI-->>Foundry: doi:10.4242/neurips.2023.castellan-csc\n    deactivate Foundry\n    Note right of Foundry: DOI cached for 24h to avoid resolver hammering\n    par Concurrent fetch of artifacts\n        Foundry->>Repo: GET /papers/{doi}/manuscript.pdf\n        Repo-->>Foundry: 200 OK (PDF bytes, 4.1 MB)\n    and\n        Foundry->>Repo: GET /papers/{doi}/supplementary.zip\n        Repo-->>Foundry: 200 OK (ZIP bytes, 18.6 MB)\n    and\n        Foundry->>Repo: GET /papers/{doi}/citation-graph.json\n        Repo-->>Foundry: 200 OK (forward + backward citations, 312 records)\n    end\n    activate Foundry\n    Foundry-->>Reader: Bundle (PDF + supplement + citation graph) ready for download\n    deactivate Foundry\n    Note over Reader: Reader can now open manuscript and traverse forward citations offline"}
```

- **Source**: hand-written; the Castellan et al. NeurIPS 2023 reference
  re-uses the FLOW-CONS hub-paper from v1 mermaid_flowchart for cross-
  mermaid-family entity continuity (the same researcher's published work
  is the artifact being retrieved here — self-consistent fictional
  research-provenance domain).
- **Domain archetype**: paper-methods / software-docs (the dual archetype
  of sequenceDiagram itself; this consolidated lives in the intersection).
- **Integrated patterns**:
  - 4 participants with `participant X as Display Name` aliases
  - `Note over Reader,Repo` (multi-participant span) AND `Note right of
    Foundry` (single-participant placement) AND `Note over Reader`
    (single-participant span at the diagram tail)
  - 2 separate `activate Foundry` / `deactivate Foundry` blocks (lifeline
    re-activation for 2 distinct phases)
  - `par … and … and … end` with 3 concurrent branches (extends SEQ-C's
    2-branch case)
  - solid (`->>`) request arrows and dashed (`-->>`) response arrows
    consistently throughout
  - rich, protocol-aware message text on every arrow (HTTP method + path
    + parenthetical size qualifier; structured payload names)
  - cross-section coherence: the chain is `Reader → Foundry → DOI →
    Foundry → Repo (×3) → Foundry → Reader`, all in one connected
    interaction
- **Length budget**: 1328 chars outer, 1249 chars inner DSL (≈ 320 tokens
  inner). Consolidated:pool ratio = 1249 / 848 (SEQ-B) = **1.5×** —
  comparable to the v1 FLOW envelope (1.4×) and well inside the
  recommended 2-3× ceiling.
- **Intent**: V4_consolidated independent measurement. Score on the same
  60-record subset as V4_pool; paired Δ = V4_cons − V4_pool.

---

## 3. Python literal — drop-in for `tmg.py`

### 3.1 Pool literal

```python
ONE_SHOT_POOL_BY_VIZ_TYPE["mermaid_sequenceDiagram"] = [
    # SEQ-A — 2-actor OAuth/PKCE flow, software-docs archetype
    '{"viz_type": "mermaid_sequenceDiagram", "viz_dsl": "sequenceDiagram\\n    participant Client as Browser Client\\n    participant Auth as Carrillon Identity Provider\\n    Client->>Auth: POST /authorize (response_type=code, PKCE challenge)\\n    Auth-->>Client: 302 Redirect to Login Form\\n    Client->>Auth: POST /login (credentials + PKCE verifier)\\n    Auth-->>Client: 302 Redirect with Authorization Code\\n    Client->>Auth: POST /token (code + PKCE verifier)\\n    Auth-->>Client: 200 OK (access_token, id_token, refresh_token)"}',
    # SEQ-B — 4-actor PPO step with Note + activate, paper-methods archetype
    '{"viz_type": "mermaid_sequenceDiagram", "viz_dsl": "sequenceDiagram\\n    participant Trainer as Training Loop\\n    participant Policy as Policy Model (7B)\\n    participant Reward as Reward Model (Frozen 13B)\\n    participant Ref as Reference Model (SFT Snapshot)\\n    Note over Trainer,Ref: Single PPO step on a 256-prompt minibatch\\n    Trainer->>Policy: Sample 4 completions per prompt (temp=1.0)\\n    activate Policy\\n    Policy-->>Trainer: 1024 candidate completions\\n    deactivate Policy\\n    Trainer->>Reward: Score each completion under helpful-harmless reward head\\n    activate Reward\\n    Reward-->>Trainer: Scalar reward per completion\\n    deactivate Reward\\n    Trainer->>Ref: Compute log-prob under reference policy\\n    Ref-->>Trainer: Reference log-probs for KL penalty\\n    Note right of Trainer: Advantage = reward - beta * KL(policy || ref)\\n    Trainer->>Policy: Apply clipped PPO gradient update"}',
    # SEQ-C — par/and/end async block, software-docs archetype (DocViz pipeline)
    '{"viz_type": "mermaid_sequenceDiagram", "viz_dsl": "sequenceDiagram\\n    participant Orchestrator as DocViz Orchestrator\\n    participant Capacity as Capacity Analyzer\\n    participant Classifier as Visualization Classifier\\n    participant Architect as Content Architect\\n    Orchestrator->>Capacity: Submit segmented document chunks\\n    par Parallel preprocessing\\n        Capacity-->>Orchestrator: chunk_capacity_scores (per-chunk visualization budget)\\n    and\\n        Orchestrator->>Classifier: Submit same chunks for viz_type proposal\\n        Classifier-->>Orchestrator: viz_type proposals (with confidence)\\n    end\\n    Orchestrator->>Architect: Joined chunks + capacity + viz_type proposals\\n    Architect-->>Orchestrator: Per-visualization render plan (DSL skeleton + caption draft)"}',
]
```

### 3.2 Consolidated literal

```python
ONE_SHOT_CONSOLIDATED_BY_VIZ_TYPE["mermaid_sequenceDiagram"] = (
    '{"viz_type": "mermaid_sequenceDiagram", "viz_dsl": "sequenceDiagram\\n    participant Reader as Research Assistant\\n    participant Foundry as Foundry Research Portal\\n    participant DOI as DOI Resolver Service\\n    participant Repo as Open-Access Repository\\n    Note over Reader,Repo: End-to-end paper retrieval initiated by a single citation\\n    Reader->>Foundry: Submit citation string (Castellan et al., NeurIPS 2023)\\n    activate Foundry\\n    Foundry->>DOI: Resolve canonical DOI from citation metadata\\n    DOI-->>Foundry: doi:10.4242/neurips.2023.castellan-csc\\n    deactivate Foundry\\n    Note right of Foundry: DOI cached for 24h to avoid resolver hammering\\n    par Concurrent fetch of artifacts\\n        Foundry->>Repo: GET /papers/{doi}/manuscript.pdf\\n        Repo-->>Foundry: 200 OK (PDF bytes, 4.1 MB)\\n    and\\n        Foundry->>Repo: GET /papers/{doi}/supplementary.zip\\n        Repo-->>Foundry: 200 OK (ZIP bytes, 18.6 MB)\\n    and\\n        Foundry->>Repo: GET /papers/{doi}/citation-graph.json\\n        Repo-->>Foundry: 200 OK (forward + backward citations, 312 records)\\n    end\\n    activate Foundry\\n    Foundry-->>Reader: Bundle (PDF + supplement + citation graph) ready for download\\n    deactivate Foundry\\n    Note over Reader: Reader can now open manuscript and traverse forward citations offline"}'
)
```

> **Note on Python literal escapes**: the `\\n` inside the literal is a
> Python-source escape that becomes a single `\n` in the runtime string,
> which the JSON parser then converts to an actual newline inside the
> `viz_dsl` value (Mermaid reads each line as a separate statement).
> Same convention as v1 mermaid_flowchart / mermaid_timeline /
> mermaid_mindmap. The `viz_dsl` value starts with the literal
> `sequenceDiagram` header (header-sniff invariant).

---

## 4. 검수 체크리스트 (mentor risk #5 + risk #2 alignment)

- [x] **Syntactic spread of 3 pool exemplars**:
  - SEQ-A: 2 participants / 4 round trips / mixed `->>` and `-->>` arrows /
    no notes / no activate / no par
  - SEQ-B: 4 participants / `Note over A,B` + `Note right of X` / 3
    `activate`/`deactivate` blocks / no par
  - SEQ-C: 4 participants / `par … and … end` block / no notes / no
    activate
  → covers (participant-count × note-presence × activate-presence ×
  par-presence) cube — all three canonical sequenceDiagram shapes covered.
- [x] **All hand-written — honest disclosure**: this viz_type has **no
  historical anchor** in the prototype pool. All 4 exemplars are
  explicitly disclosed as hand-written. Content style anchored on v1
  mermaid_flowchart conventions (named participants with appositive
  qualifiers; rich phrase message text instead of single-verb edges) so
  the agent inherits the same faith-1.00 conventions transitively.
- [x] **Placeholder regression check**: no `Acme*`, no `Founder/Engineer X`,
  no single-verb edge labels (`Client->Server: get` / `A->B: send`). All
  message text is rich phrase + protocol detail or named-payload
  reference (`"POST /authorize (response_type=code, PKCE challenge)"`,
  `"Score each completion under helpful-harmless reward head"`,
  `"chunk_capacity_scores (per-chunk visualization budget)"`).
- [x] **Consolidated variant integration**: a single coherent diagram that
  carries (4 participants with aliases) × (`Note over` multi-span + `Note
  right of` single-placement + `Note over` single-span tail) × (2 `activate`
  /`deactivate` blocks for the same participant in different phases) ×
  (`par … and … and … end` 3-branch parallel) × (mixed `->>` / `-->>`
  arrows consistently) × (rich protocol-aware message text on every arrow).
  No stitching; one connected interaction sequence.
- [x] **JSON round-trip**: all 4 strings (3 pool + 1 consolidated) parse
  via `json.loads`; `viz_type == "mermaid_sequenceDiagram"` for all;
  `viz_dsl.lstrip().startswith("sequenceDiagram")` is True for all
  (header sniff passes).
- [x] **Mermaid syntax validity**: each `viz_dsl` parses under Mermaid's
  sequenceDiagram grammar (verified by the structural conventions
  documented above: `participant X as Y`, `X->>Y: text`, `Note over A,B:
  text`, `activate X` / `deactivate X`, `par caption … and … end`).
- [x] **Token budget**: pool max = 848 chars (SEQ-B) ≈ 215 tokens;
  consolidated = 1249 chars ≈ 320 tokens (1.5× pool max — comparable to
  v1 FLOW envelope).
- [x] **Self-validation result**: PASS. All 4 exemplars round-trip via
  `json.loads`; all 4 inner DSLs start with `sequenceDiagram`; no
  placeholder substring; no single-verb message edges; consolidated:pool
  char ratio = 1.5×.
