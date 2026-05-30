# docqa / parsing tool — document flow policy

This document is shared background for anyone touching the docqa_tools or
parsing_tools modules on either `master` (production) or `sft-gen-ir-shim`
(SFT data generation). Each module's docstring points back here so the
maintenance background does not get duplicated or rot per file.

## Roles

- **Files API** (`POST/GET/DELETE /v1/files` at e.g. `https://api.lgresearch.ai/...`
  or `https://dev-api.lgresearch.ai/...`) — high-level layer. Accepts raw
  document bytes, returns `id` (= `fid`), exposes `status` (ready / processing
  / failed) once the parser pre-build has run.
- **IR endpoint** (`http://gw-qa.lgair.net/api/lang/search/chatexaone` or
  similar) — low-level. Request types: `add`, `search_fid`, `remove_file`,
  `all_fids`, `count_fids`. `search_fid` with `search_pass=1` returns the
  indexed pages for the given fids *without* running a search query, which
  doubles as a "is this fid already indexed?" probe.
- **Parser** (`DOC_PARSER`) — raw bytes → per-page `html_parsed` /
  `list_parsed` chunk dicts. Called explicitly by the lgair-style flow;
  called implicitly by the Files API path (server-side, before status=ready).
- **Selector** (`SELECTOR`) — **no longer used** by either branch's IR path
  for ranking. IR's own `score` field is used directly. (ir-shim Mode A
  still calls a different `sft_pipeline` selector locally — see below.)

## Flows

### Production (`master`)

```
[upstream system or Files API layer]
   │  uploads raw file, assigns fid
   ▼
[main agent receives one or more fids]
   ▼
parse_web_and_doc(file_ids):
   1. For each fid: IR find_docs(search_pass=1, fids=[fid]) → pages or empty.
   2. Pages present → rehydrate cache from IR (chunk + page metadata),
      mark ir_source=True. No parser call.
   3. Empty → parse_document(parser HTTP) → add_doc(IR) → cache,
      mark parser_source=True.

doc_search(queries, doc_ids):
   - IR find_docs(rerank=1, fids=[...]) per query.
   - Use the response's `score` field directly for ranking.
   - No selector call.
```

Notes:

- The upstream-issued fid is assumed. If a caller does not supply `file_id`,
  the handler derives a deterministic fid from `sha1(filename + first 1KiB)`
  for compatibility with deployments where the upstream layer is absent —
  but production callers normally provide it.
- The IR/parser wire format matches lgair `doc_dao.create_doc` /
  `doc_search_service.execute` exactly so any deployment that previously
  pointed at those services keeps working.

### ir-shim — Mode A (`HERMES_DOC_SOURCE=local`, default)

Used by the SFT data-generation pipeline when running against the local
docai corpus.

```
[SFT top-level script]
   │  raw PDF paths + locally pre-parsed JSON paths
   ▼
parse_web_and_doc(document_idx):
   - file_mapping.json lookup → pre-parsed JSON load.
   - No parser HTTP call, no IR `add`.

doc_search(queries, document_idx):
   - sft_pipeline selector (HTTP) ranks the pages directly.
   - No IR call.
```

This path is SFT-only and does not exist on `master`.

### ir-shim — Mode B (`HERMES_DOC_SOURCE=remote`)

Used by SFT batches that want the production codepath end-to-end. The
SFT environment does not have an upstream system to assign fids, so
ir-shim must upload the file itself to the dev Files API and propagate
the returned fid into the main agent session.

```
[SFT top-level script]
   │  raw document files
   ▼
[ir-shim Mode B uploader: exaone/sft_gen/upload_to_ir.py]
   │  POST <dev>/v1/files with API key → fid per file
   │  inject into per-task attachment table
   ▼
[main agent receives one or more fids — same shape as production]
   ▼
parse_web_and_doc / doc_search: identical to production flow above.
```

The Files API takes care of running the parser before reporting `status=ready`,
so the IR `search_pass=1` probe inside `parse_web_and_doc` will return pages and the
agent skips the local parser call. This matches what production sees when
the upstream system has already pre-built parse artifacts.

## Cache shape

`exaone/docqa_tools/_doc_cache.py` stores per-task documents as a list of
`CachedChunk(text, html, page)`. IR's `add`/`search_fid` operate per chunk
and one page can carry multiple chunks (see `meta_data.chunk_to_page`), so
the cache preserves the chunk granularity. Consumer tools roll chunks back
up to per-page text where needed:

- `get_document_chunks(<fid>-<page>)`: gather chunks where chunk.page == page,
  join with `\n\n`.
- `ReadFullDocument`: gather all chunks, sort by `(0, int(page))` for digit
  pages and `(1, page)` for named pages, join.

## What differs between branches at the file level

| Concern | master | ir-shim |
|---|---|---|
| `parse_web_and_doc` schema | `file_path` / `file_url` / `file_bytes_b64` + `filename` | `document_idx` (idx-only) — attachment table resolves the fid |
| `parse_web_and_doc` flow | Single IR-backed flow. | Mode A=local JSON; Mode B=IR flow (identical to master). |
| `doc_search` envelope | Mirror `{success, results, data: {doc: results}}` for `RunIndexStore` compatibility. | Single `{success, results}` (citation envelope unified by `91cf2018`). |
| `CachedChunk` cache | Same shape. | Same shape. |
| Selector | Removed. | Removed for IR path. Mode A keeps its `sft_pipeline` selector locally. |
| Env source flag | none. | `HERMES_DOC_SOURCE=local|remote` chooses Mode A vs B. |

When porting fixes between branches, the schema and envelope differences are
intentional — do NOT homogenize them without updating this document first.

## Shared logic files (byte-identical on both branches)

The files below are kept byte-identical on `master` and `sft-gen-ir-shim`.
Each carries a `## SHARED LOGIC` section at the top of its docstring pointing
back here. When you edit one, copy the result to the other branch in the same
patch — cherry-picking shared-file fixes between branches should be a clean
`cp` with zero conflicts.

| File | Notes |
|---|---|
| `exaone/docqa_tools/_policy.md` | This document. |
| `exaone/docqa_tools/_ir_client.py` | Lgair IR wire client. |
| `exaone/docqa_tools/_doc_cache.py` | Per-task chunk cache + IR rehydrate. Includes the ir-shim-only `doc_to_page_dicts` helper at the bottom; it is dead code on master and stays there for diff-zero — do not delete. |
| `exaone/auxiliary_tracer.py` | Up to (and including) `write_rd_extract_log`. The VLM/OCR helpers below that point are ir-shim-only (mm_docqa scope) and must NOT be cherry-picked to master. |
| `exaone/docqa_tools/handle_list_documents.py` | Schema, handler, envelope shape 양 브랜치 동일. Output 은 idx + filename + parsed flag + page_count + char_count 만 노출 — fid/ir_status 같은 내부정보 노출 X. |

## Intentional divergence (kept separate, do not homogenise)

| File | Why it differs |
|---|---|
| `exaone/parsing_tools/handle_parse_web_and_doc.py` | Master schema = doc 분기는 `file_path`/`file_url`/`file_bytes_b64`/`file_id` + filename. ir-shim schema = doc 분기는 `document_idx` (idx-only). 두 브랜치 모두 web 분기는 `urls: list[str]` (web_extract 와 동일 키). ir-shim 은 Mode A/B 분기 (`HERMES_DOC_SOURCE`) 도 가짐. |
| `exaone/docqa_tools/handle_doc_search.py` | Master schema = `document_file_ids` + `public_document_file_ids` (lgair-* fid sourcing 규약, union 하여 IR fids). ir-shim schema = `document_idx`. ir-shim 은 Mode A path 에서 `sft_pipeline` selector 사용. 두 브랜치가 IR 에 넣는 fid pool 의 의미는 동일 — ir-shim 의 attachment table 이 lgair 의 union 모집단을 결과적으로 제공한다고 가정. |
| `exaone/docqa_tools/handle_get_document_chunks.py` | Input format: master uses `<file_id>-<page>`, ir-shim uses `<document_idx>-<page>`. |
| `exaone/docqa_tools/handle_read_full_document.py` | Master takes `file_id`. ir-shim takes `document_idx` and adds an extractor retry loop. |
| `exaone/qa_modes.py` | Master has `taskbot`. ir-shim has `taskbot` + `mm_docqa` (multimodal — visual_tools, page-layout). |
| `exaone/sft_gen/` | ir-shim only — SFT pipeline, Dev Files API uploader, batch runner. None of this exists on master. |

The handler files share a per-page-block grouping pattern, sort key, and
EXTRACTOR aux-call resolver. When you change that pattern, mirror it on both
branches even though the schema headers differ.
