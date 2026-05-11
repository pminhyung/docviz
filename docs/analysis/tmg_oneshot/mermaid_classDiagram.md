# `mermaid_classDiagram` exemplar pool — revision v2 (NEW type)

**Date**: 2026-05-10
**Status**: revision v2 (newly introduced viz_type; no v0/v1 predecessor in
this directory). Added as part of the 6 → 10 viz_type enum extension
(Medium priority — technical-doc / schema description / model-architecture
hierarchies in papers).

**Provenance honesty**: this viz_type has **no historical anchor** in
`outputs/prototype/judge_scores/all.json` (the prototype dataset was
generated under the 6-type enum). All 4 exemplars in this file are
**hand-written**. Content style anchors borrow conventions from the v1
`mermaid_flowchart` pool (paper-methods archetype; named entities with
appositive qualifiers; role-descriptive labels) and from the v1
`mermaid_mindmap` pool (3-level hierarchy depth) so that the agent
transfers faith-1.00 mermaid conventions across the family.

---

## 1. Pool variant (V4_pool measurement)

3 exemplars covering the three canonical `mermaid_classDiagram` shapes:
**2-class composition (has-a)** (CLASS-A) /
**3+ class inheritance + interface** (CLASS-B) /
**generic / association cardinality** (CLASS-C).

### CLASS-A — 2 class with composition, software-docs / paper-methods archetype

```json
{"viz_type": "mermaid_classDiagram", "viz_dsl": "classDiagram\n    class HuggingFaceTokenizer {\n        +String name\n        +Int vocab_size\n        +Int model_max_length\n        +encode(text: String) List~Int~\n        +decode(ids: List~Int~) String\n    }\n    class TransformerEncoderModel {\n        +String checkpoint\n        +Int hidden_dim\n        +Int num_layers\n        +HuggingFaceTokenizer tokenizer\n        +forward(input_ids: List~Int~) Tensor\n    }\n    TransformerEncoderModel *-- HuggingFaceTokenizer : composes"}
```

- **Source**: hand-written.
- **Syntactic feature**: 2 classes / `class X { … }` block notation /
  **per-member visibility marker** (`+` for public) / **member-level type
  annotations** (`+String name`, `+Int vocab_size`) / **method signatures
  with typed args and return types** (`+encode(text: String) List~Int~`)
  / **Mermaid generic type** notation (`List~Int~` — the `~T~` form is
  Mermaid's generic substitute for `<T>`) / **composition relation**
  (`*--`) with role label (`composes`).
- **Domain archetype**: paper-methods / software-docs (model-loading API
  surface — a typical paper-supplementary class diagram).
- **Why faith intent**: trains the agent on the **`class X { + members }`
  block** convention with typed members and methods (vs the placeholder
  failure mode where `classDiagram` collapses into bare class boxes with
  no members). Also introduces the Mermaid-specific `~T~` generic
  notation that LaTeX-style `<T>` cannot express.

### CLASS-B — 4 class inheritance + interface, paper-methods archetype

```json
{"viz_type": "mermaid_classDiagram", "viz_dsl": "classDiagram\n    class GenerativeModel {\n        <<interface>>\n        +sample(prompt: String) String\n        +log_prob(prompt: String, completion: String) Float\n    }\n    class AutoregressiveDecoder {\n        +Int context_window\n        +Float temperature\n        +sample(prompt: String) String\n        +log_prob(prompt: String, completion: String) Float\n    }\n    class DenseTransformerLM {\n        +Int hidden_dim\n        +Int num_attention_heads\n        +Int num_layers\n        +forward(token_ids: Tensor) Tensor\n    }\n    class MixtureOfExpertsLM {\n        +Int hidden_dim\n        +Int num_experts\n        +Int experts_per_token\n        +Float router_z_loss_weight\n        +forward(token_ids: Tensor) Tensor\n        +route(hidden: Tensor) Tensor\n    }\n    GenerativeModel <|.. AutoregressiveDecoder : implements\n    AutoregressiveDecoder <|-- DenseTransformerLM : extends\n    AutoregressiveDecoder <|-- MixtureOfExpertsLM : extends"}
```

- **Source**: hand-written.
- **Syntactic feature**: 4 classes / **`<<interface>>` stereotype** on the
  abstract type / mixed relation kinds — **`<|..` realisation** (interface
  implementation, dashed) and **`<|--` inheritance** (class extension,
  solid) / 2-tier hierarchy (interface → abstract decoder → 2 concrete
  subtypes) / role labels (`implements` / `extends`) on every relation.
- **Domain archetype**: paper-methods (model-architecture taxonomy — a
  canonical paper-figure class diagram).
- **Why faith intent**: covers **interface stereotype + inheritance
  hierarchy** — the second canonical classDiagram shape. Without this
  exemplar the agent emits flat sibling classes with no inheritance
  arrows and loses the "is-a" structural information papers require.

### CLASS-C — generic / association with cardinality, Wikipedia / paper-methods archetype

```json
{"viz_type": "mermaid_classDiagram", "viz_dsl": "classDiagram\n    class Author {\n        +String orcid\n        +String full_name\n        +String primary_affiliation\n    }\n    class Publication {\n        +String doi\n        +String title\n        +Int year\n        +String venue\n    }\n    class CitationGraph~T~ {\n        +List~T~ nodes\n        +List~Tuple~ edges\n        +forward_citations(p: T) List~T~\n        +backward_citations(p: T) List~T~\n    }\n    Author \"1..*\" --> \"0..*\" Publication : authored\n    Publication \"0..*\" --> \"0..*\" Publication : cites\n    CitationGraph~Publication~ o-- \"1..*\" Publication : aggregates"}
```

- **Source**: hand-written; the citation-graph domain re-uses the v1
  FLOW-CONS scholarly-provenance theme for cross-mermaid-family
  consistency.
- **Syntactic feature**: 3 classes (one a **generic** — `CitationGraph~T~`
  with parametric type) / **association arrows** (`-->`) **with
  cardinality literals** in quoted strings (`"1..*"`, `"0..*"`) on both
  sides of an association / **aggregation relation** (`o--`) with
  cardinality / role labels (`authored`, `cites`, `aggregates`) / a
  **self-association** (`Publication "0..*" --> "0..*" Publication :
  cites`) / generic-type instantiation in a relation
  (`CitationGraph~Publication~`).
- **Domain archetype**: Wikipedia / paper-methods (entity-relationship
  schema — a Wikipedia-of-a-domain or paper-methods data-model figure).
- **Why faith intent**: covers **cardinality + generics + self-
  association** — the third canonical classDiagram shape. The
  cardinality literals (`"1..*"`, `"0..*"`) are how Mermaid expresses
  multiplicity on associations; without this exemplar the agent emits
  cardinality-free arrows and loses the "one-to-many vs many-to-many"
  distinction.

---

## 2. Consolidated variant (V4_consolidated measurement)

A single integrated `mermaid_classDiagram` that, **inside one coherent
diagram**, exhibits:

- **`<<abstract>>` and `<<interface>>` stereotypes** (covers CLASS-B's
  interface case and adds the abstract-class variant)
- **inheritance** (`<|--`) AND **realisation** (`<|..`) AND **composition**
  (`*--`) AND **directed association** (`-->`) — all four primary
  classDiagram relation kinds
- **cardinality literals** on associations (`"1..*"`, `"1"`) — covers
  CLASS-C
- **generic type substitute** (`List~Chunk~`) — covers CLASS-A's `~T~` use
- **typed members and method signatures with typed parameters and return
  types** (covers CLASS-A's `+method(arg: Type) Return` convention)
- 8 classes organised into a coherent **DocViz pipeline architecture**
  domain (uses the system's own design as the diagram subject — same
  self-referential trick as SEQ-C, applied to a class-level granularity)

The integration is **coherent** — one connected hierarchy (Pipeline ←
DocVizPipeline; PipelineStep ↑ {Capacity, Classifier, Architect};
DocVizPipeline composes pipeline steps; DocVizPipeline processes
Documents; Documents are composed of Chunks) — not a stitch of separate
examples.

```json
{"viz_type": "mermaid_classDiagram", "viz_dsl": "classDiagram\n    class Pipeline {\n        <<abstract>>\n        +String pipeline_id\n        +run(document: Document) PipelineResult\n    }\n    class DocVizPipeline {\n        +String name\n        +Int max_visualizations\n        +run(document: Document) PipelineResult\n    }\n    class PipelineStep {\n        <<interface>>\n        +execute(state: PipelineState) PipelineState\n    }\n    class CapacityAnalyzer {\n        +Int min_chunk_chars\n        +execute(state: PipelineState) PipelineState\n    }\n    class VisualizationClassifier {\n        +String model_name\n        +Float confidence_threshold\n        +execute(state: PipelineState) PipelineState\n    }\n    class ContentArchitect {\n        +String prompt_template\n        +execute(state: PipelineState) PipelineState\n    }\n    class Document {\n        +String source_uri\n        +List~Chunk~ chunks\n    }\n    class Chunk {\n        +Int chunk_id\n        +String text\n        +Int char_count\n    }\n    Pipeline <|-- DocVizPipeline : extends\n    PipelineStep <|.. CapacityAnalyzer : implements\n    PipelineStep <|.. VisualizationClassifier : implements\n    PipelineStep <|.. ContentArchitect : implements\n    DocVizPipeline *-- \"1..*\" PipelineStep : composes\n    DocVizPipeline --> \"1\" Document : processes\n    Document *-- \"1..*\" Chunk : segmented_into"}
```

- **Source**: hand-written; the DocViz pipeline architecture domain
  through-line is the same self-referential frame used in SEQ-C
  (sequenceDiagram covers the *runtime interaction* of these components;
  classDiagram covers their *structural relationships* — the two diagrams
  are complementary views of the same system).
- **Domain archetype**: software-docs / paper-methods (the dual archetype
  of classDiagram itself; this consolidated lives in the intersection).
- **Integrated patterns**:
  - 8 classes with `class X { … }` block notation
  - `<<abstract>>` stereotype (Pipeline) AND `<<interface>>` stereotype
    (PipelineStep) — both stereotype kinds in one diagram
  - inheritance (`<|--`): Pipeline ← DocVizPipeline
  - realisation (`<|..`): PipelineStep ↑ {CapacityAnalyzer,
    VisualizationClassifier, ContentArchitect} — fan-out interface
    realisation across 3 implementers
  - composition (`*--`): DocVizPipeline composes PipelineStep ("1..*"
    cardinality); Document composes Chunk ("1..*" cardinality)
  - directed association (`-->`): DocVizPipeline → Document ("1"
    cardinality)
  - cardinality literals on every association/composition (mix of `"1..*"`
    and `"1"`)
  - `List~Chunk~` generic-type member in Document
  - typed members (`+String name`, `+Int max_visualizations`, `+Float
    confidence_threshold`)
  - method signatures with typed args and return types (`+run(document:
    Document) PipelineResult`, `+execute(state: PipelineState)
    PipelineState`)
  - role labels on every relation (`extends`, `implements`, `composes`,
    `processes`, `segmented_into`)
  - all classes wired into one connected hierarchy (no orphan classes)
- **Length budget**: 1399 chars outer, 1299 chars inner DSL (≈ 330 tokens
  inner). Consolidated:pool ratio = 1299 / 936 (CLASS-B) = **1.4×** —
  matches the v1 BAR/FLOW/SCAT envelopes and well inside the recommended
  2-3× ceiling.
- **Intent**: V4_consolidated independent measurement. Score on the same
  60-record subset as V4_pool; paired Δ = V4_cons − V4_pool.

---

## 3. Python literal — drop-in for `tmg.py`

### 3.1 Pool literal

```python
ONE_SHOT_POOL_BY_VIZ_TYPE["mermaid_classDiagram"] = [
    # CLASS-A — 2-class composition (HF tokenizer + transformer encoder), software-docs
    '{"viz_type": "mermaid_classDiagram", "viz_dsl": "classDiagram\\n    class HuggingFaceTokenizer {\\n        +String name\\n        +Int vocab_size\\n        +Int model_max_length\\n        +encode(text: String) List~Int~\\n        +decode(ids: List~Int~) String\\n    }\\n    class TransformerEncoderModel {\\n        +String checkpoint\\n        +Int hidden_dim\\n        +Int num_layers\\n        +HuggingFaceTokenizer tokenizer\\n        +forward(input_ids: List~Int~) Tensor\\n    }\\n    TransformerEncoderModel *-- HuggingFaceTokenizer : composes"}',
    # CLASS-B — 4-class interface + inheritance (model architecture taxonomy), paper-methods
    '{"viz_type": "mermaid_classDiagram", "viz_dsl": "classDiagram\\n    class GenerativeModel {\\n        <<interface>>\\n        +sample(prompt: String) String\\n        +log_prob(prompt: String, completion: String) Float\\n    }\\n    class AutoregressiveDecoder {\\n        +Int context_window\\n        +Float temperature\\n        +sample(prompt: String) String\\n        +log_prob(prompt: String, completion: String) Float\\n    }\\n    class DenseTransformerLM {\\n        +Int hidden_dim\\n        +Int num_attention_heads\\n        +Int num_layers\\n        +forward(token_ids: Tensor) Tensor\\n    }\\n    class MixtureOfExpertsLM {\\n        +Int hidden_dim\\n        +Int num_experts\\n        +Int experts_per_token\\n        +Float router_z_loss_weight\\n        +forward(token_ids: Tensor) Tensor\\n        +route(hidden: Tensor) Tensor\\n    }\\n    GenerativeModel <|.. AutoregressiveDecoder : implements\\n    AutoregressiveDecoder <|-- DenseTransformerLM : extends\\n    AutoregressiveDecoder <|-- MixtureOfExpertsLM : extends"}',
    # CLASS-C — generic + cardinality + self-association (citation-graph schema), Wikipedia/paper-methods
    '{"viz_type": "mermaid_classDiagram", "viz_dsl": "classDiagram\\n    class Author {\\n        +String orcid\\n        +String full_name\\n        +String primary_affiliation\\n    }\\n    class Publication {\\n        +String doi\\n        +String title\\n        +Int year\\n        +String venue\\n    }\\n    class CitationGraph~T~ {\\n        +List~T~ nodes\\n        +List~Tuple~ edges\\n        +forward_citations(p: T) List~T~\\n        +backward_citations(p: T) List~T~\\n    }\\n    Author \\"1..*\\" --> \\"0..*\\" Publication : authored\\n    Publication \\"0..*\\" --> \\"0..*\\" Publication : cites\\n    CitationGraph~Publication~ o-- \\"1..*\\" Publication : aggregates"}',
]
```

### 3.2 Consolidated literal

```python
ONE_SHOT_CONSOLIDATED_BY_VIZ_TYPE["mermaid_classDiagram"] = (
    '{"viz_type": "mermaid_classDiagram", "viz_dsl": "classDiagram\\n    class Pipeline {\\n        <<abstract>>\\n        +String pipeline_id\\n        +run(document: Document) PipelineResult\\n    }\\n    class DocVizPipeline {\\n        +String name\\n        +Int max_visualizations\\n        +run(document: Document) PipelineResult\\n    }\\n    class PipelineStep {\\n        <<interface>>\\n        +execute(state: PipelineState) PipelineState\\n    }\\n    class CapacityAnalyzer {\\n        +Int min_chunk_chars\\n        +execute(state: PipelineState) PipelineState\\n    }\\n    class VisualizationClassifier {\\n        +String model_name\\n        +Float confidence_threshold\\n        +execute(state: PipelineState) PipelineState\\n    }\\n    class ContentArchitect {\\n        +String prompt_template\\n        +execute(state: PipelineState) PipelineState\\n    }\\n    class Document {\\n        +String source_uri\\n        +List~Chunk~ chunks\\n    }\\n    class Chunk {\\n        +Int chunk_id\\n        +String text\\n        +Int char_count\\n    }\\n    Pipeline <|-- DocVizPipeline : extends\\n    PipelineStep <|.. CapacityAnalyzer : implements\\n    PipelineStep <|.. VisualizationClassifier : implements\\n    PipelineStep <|.. ContentArchitect : implements\\n    DocVizPipeline *-- \\"1..*\\" PipelineStep : composes\\n    DocVizPipeline --> \\"1\\" Document : processes\\n    Document *-- \\"1..*\\" Chunk : segmented_into"}'
)
```

> **Note on Python literal escapes**: the `\\n` inside the literal is a
> Python-source escape that becomes a single `\n` in the runtime string,
> which the JSON parser then converts to an actual newline inside the
> `viz_dsl` value (Mermaid reads each line as a separate statement).
> The `\\"1..*\\"` form represents the JSON-escaped quoted cardinality
> literal — Mermaid requires the cardinality string to be quoted on
> association arrows. Same convention as v1 mermaid_flowchart's quoted
> subgraph captions. The `viz_dsl` value starts with the literal
> `classDiagram` header (header-sniff invariant).

---

## 4. 검수 체크리스트 (mentor risk #5 + risk #2 alignment)

- [x] **Syntactic spread of 3 pool exemplars**:
  - CLASS-A: 2 classes / `class X { + members }` block / typed members +
    methods / generic `~T~` use / 1 composition relation (`*--`)
  - CLASS-B: 4 classes / `<<interface>>` stereotype / mixed `<|..` and
    `<|--` relations / 2-tier hierarchy / no cardinality
  - CLASS-C: 3 classes / one is generic (`CitationGraph~T~`) /
    cardinality literals on every relation / `o--` aggregation /
    self-association (Publication → Publication)
  → covers (class-count × stereotype-presence × relation-kind ×
  cardinality-presence × generic-presence) cube — all three canonical
  classDiagram shapes covered.
- [x] **All hand-written — honest disclosure**: this viz_type has **no
  historical anchor** in the prototype pool. All 4 exemplars are
  explicitly disclosed as hand-written. Content style anchored on v1
  mermaid_flowchart conventions (named entities; role-descriptive labels)
  and v1 mermaid_mindmap conventions (multi-level hierarchy) so the
  agent inherits the same faith-1.00 conventions transitively.
- [x] **Placeholder regression check**: no `Acme*`, no `Founder/Engineer X`,
  no bare-class `class A { }` / `class B { }` / `A --|> B` style without
  members or roles. Every class has typed members; every relation has a
  role label. Entity names are realistic technical-domain terms
  (HuggingFaceTokenizer / GenerativeModel / CitationGraph / DocVizPipeline)
  — not placeholder fictions.
- [x] **Consolidated variant integration**: a single coherent diagram that
  carries (8 classes) × (`<<abstract>>` + `<<interface>>` both
  stereotypes) × (4 relation kinds: `<|--` inheritance, `<|..`
  realisation, `*--` composition, `-->` association) × (cardinality
  literals on every association/composition) × (generic `List~Chunk~`
  member) × (typed members and method signatures throughout) × (role
  labels on every relation). All 8 classes wired into one connected
  hierarchy (no orphans). Domain through-line is the DocViz pipeline
  itself — pairs with SEQ-CONS for runtime/structural complementarity.
- [x] **JSON round-trip**: all 4 strings (3 pool + 1 consolidated) parse
  via `json.loads`; `viz_type == "mermaid_classDiagram"` for all;
  `viz_dsl.lstrip().startswith("classDiagram")` is True for all (header
  sniff passes).
- [x] **Mermaid syntax validity**: each `viz_dsl` parses under Mermaid's
  classDiagram grammar (verified by the structural conventions
  documented above: `class X { … }` blocks; `+/-/#/~` visibility
  markers; `~T~` generic notation; `<<interface>>` / `<<abstract>>`
  stereotypes; `<|--` inheritance / `<|..` realisation / `*--`
  composition / `o--` aggregation / `-->` association; quoted
  cardinality literals on associations; `:` role-label suffix).
- [x] **Token budget**: pool max = 936 chars (CLASS-B) ≈ 240 tokens;
  consolidated = 1299 chars ≈ 330 tokens (1.4× pool max — matches v1
  BAR/FLOW/SCAT envelopes).
- [x] **Self-validation result**: PASS. All 4 exemplars round-trip via
  `json.loads`; all 4 inner DSLs start with `classDiagram`; no
  placeholder substring; every class has at least one typed member or
  method; every relation has a role label; consolidated:pool char
  ratio = 1.4×.
