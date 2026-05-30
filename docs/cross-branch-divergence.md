# Cross-branch divergence report

대상 독자: upstream
`/ex_disk2/mhpark/upload/chatexaone-agent-harness` 로 MR 을 준비하는
사람, 또는 `master` 와 `sft-gen-ir-shim` 사이에 변경을 port 하는 사람.

이 파일이 정리하는 내용:
- LG 측 reference repo (upload) 와의 불가피한 차이.
- `master` 와 `sft-gen-ir-shim` 사이의 의도적 차이.
- 아직 처리해야 할 위반 사항 / 표류 (drift).

docqa surface 의 machine-readable cross-branch sync 계약은
`exaone/docqa_tools/_policy.md` 에 있음. `exaone/docqa_tools/` 또는
`exaone/parsing_tools/` 안의 파일을 편집할 때는 그 파일을 먼저 읽을 것.

일상 작업 룰은 `docs/master_rule.md` 와 `docs/ir-shim_rule.md` 참고.

## 섹션 상태 한눈에 보기

| 섹션 | 상태 | 무엇을 의미하는가 |
|---|---|---|
| §1 master vs upload 의도적 차이 | 적용됨 | 현재 master 코드에 이미 있음. 유지. MR 시 LG 에 설명. |
| §2 master vs ir-shim 의도적 차이 | 적용됨 | 현재 양 브랜치 코드에 이미 있음. 동일화 금지. |
| §3.1 master 의 AGENTS.md/test_rule.md 위반 | **미적용** | 현재 master 에 단위/스모크 테스트 없음. **MR 전 반드시 처리.** |
| §3.2 master 스타일 결함 | **미적용** | 프롬프트-스키마 drift, heading 비일관 등. **MR 전 정리 권장.** |
| §3.3 ir-shim 정당화 안 된 drift | **미적용** | ir-shim 코드에 남아 있는 drift. 다음 ir-shim 사이클에 처리. |
| §3.4 master 가 흡수하면 좋을 ir-shim 측 개선 | **미적용 (선택)** | ir-shim 에는 있지만 master 에는 없음. blocker 아님. |

---

## 1. master 가 upload 와 불가피하게 다른 부분

> **상태: [이미 적용됨 — 의도적으로 유지]**
> 아래 4개 항목은 모두 현재 master 코드에 들어가 있음.
> 권장 처리: 이대로 유지. MR 리뷰 시 LG 측에 사유와 함께 설명하면 됨.

범위: **AGENTS.md 가 허용하는 fork 확장이 아닌** 차이만 정리. 아래
항목들은 upstream 측에는 없는 제약(우리가 두 브랜치를 병행 운영함,
멀티 워크트리 harness 사용, 브랜치 간 shared logic 동기화 유지)
때문에 master 에 들어가 있는 것들.

**이 섹션의 범위 밖 (= AGENTS.md 룰이 명시적으로 허용하는 fork 확장)**:

- `exaone/docqa_tools/`, `exaone/parsing_tools/` 신규 패키지 + `exaone/tools.py`
  안에서 `registry.register(...)` + `create_custom_toolset(EXAONE_TOOLSET_NAME, …)`
  로 등록. AGENTS.md §"Adding New Tools" L272-281 + L283-310 이
  fork-customization 경로로 명시 허용.
- `QA_MODES` 에 새 모드(`docqa`, `taskbot`) 추가 — upstream 의
  `general` / `research` / `canvas` 와 동일 패턴.
- `auxiliary_tracer.write_rd_extract_log` — 기존
  `{compression, web_extract, finalizer}` family 확장. 파일 shape 동일,
  `_CURRENT_RUN_DIR` 바인딩 그대로 재사용.
- IR / parser microservice client (`_ir_client.py`, `_parser_client.py`) —
  lgair production wire 그대로 미러. 기존 DOC_SEARCH / DOC_PARSER 를
  쓰는 배포가 zero-config 로 동작하도록.
- `registry.register(..., requires_env=..., check_fn=...)` 와
  `display_hermes_home()` / `get_hermes_home()` 룰 전 구간 준수 — 코어
  파일 무수정.

아래 네 가지가 진짜 "어쩔 수 없는" 차이.

| # | 차이 | 위치 | 왜 upload 스타일로 그냥 합칠 수 없는가 |
|---|---|---|---|
| 1 | `exaone/docqa_tools/_policy.md` 존재, 그리고 shared 모듈들의 docstring 에 `## SHARED LOGIC` 블록(≤ 10줄). | `exaone/docqa_tools/_policy.md`; `_ir_client.py`, `_doc_cache.py`, `auxiliary_tracer.py`, 4개 `handle_*.py` 의 docstring. | `master` 와 `sft-gen-ir-shim` 을 병행 운영하면서 일부 파일을 byte-identical 로 유지해야 cherry-pick 이 zero-conflict. upstream 은 단일 브랜치라 이런 계약이 필요 없음. master 에서 이 블록을 빼면 "이 파일은 단독으로 편집하지 말 것" 이라는 유일한 신호가 사라짐. |
| 2 | `exaone/docqa_tools/_doc_cache.py::doc_to_page_dicts` 가 `master` 에서 dead code. | `exaone/docqa_tools/_doc_cache.py:280-313` (파일 끝 helper). | #1 과 같은 cross-branch byte-identity 사유. 이 helper 는 `sft-gen-ir-shim` Mode A selector 경로에서만 호출됨. master 에서 지우면 `_doc_cache.py` 가 브랜치 간 분기되어 매 shared-logic 동기화가 수동 머지로 바뀜. **MR 옵션**: MR 직전에 제거하고 이후 매번 수동 동기화 비용 감수하거나, helper 위 한 줄 주석 그대로 두고 유지. |
| 3 | `auxiliary_tracer.py` 의 `write_rd_extract_log` 이후 라인을 shared 구간(위) 과 ir-shim 전용 mm_docqa writer(아래) 의 경계선으로 예약. | `exaone/auxiliary_tracer.py` 235 라인까지가 master. | 두 브랜치 간 `auxiliary_tracer.py` 를 hunk 단위가 아닌 파일 단위로 복사할 수 있게 함. 이 cut-line 은 `_policy.md` "Shared logic files" 에 기록된 cross-branch sync 계약의 일부. |
| 4 | `.gitignore` 에 upload 에는 없는 `.harness/`, `.worktrees/`, `docs/active` 블록. | `.gitignore` 의 "harness tracking dir" 주석 주변. | 로컬 Claude-Code harness 와 멀티 워크트리 워크플로의 per-developer 상태. 순수 개발 인프라 — upload 배포 사용자에게는 영향 없음.

이 네 가지는 모두 우리가 개발하는 방식 때문에 생긴 로컬 프로세스 산물이며,
기능 변화가 아님. 런타임 동작에 영향 없고, Hermes 코어를 호출하는 코드도
새로 추가되지 않음.

## 2. `master` 와 `sft-gen-ir-shim` 사이의 의도적 차이

> **상태: [이미 적용됨 — 의도적으로 유지]**
> 아래 7개 항목은 모두 현재 양 브랜치 코드에 들어가 있음.
> 권장 처리: 이대로 유지. **`exaone/docqa_tools/_policy.md`
> 를 먼저 갱신하지 않고는 동일화 금지**.

| # | 차이 | 파일 | 이유 |
|---|---|---|---|
| 1 | 스키마 입력 포맷: `file_path` / `file_url` / `file_bytes_b64` / `file_id` vs `document_idx` | `parsing_tools/handle_doc_parsing.py`, `docqa_tools/handle_doc_search.py`, `handle_find_documents.py`, `handle_get_document_chunks.py`, `handle_read_full_document.py`, 모든 `prompts/tools/*.txt` | ir-shim 의 SFT 프롬프트가 `[Attached documents]` 블록을 주입해 모델이 raw path / UUID 를 보지 않게 함. master 의 production 호출자는 upstream 이 발급한 `file_id` (또는 전체 bytes) 를 들고 들어옴. |
| 2 | `HERMES_DOC_SOURCE` 기반 Mode A / Mode B 분기 | `docqa_tools/_doc_source.py` (ir-shim 전용), 모든 docqa handler 안의 Mode A `_handle_*_shim` 경로, `parsing_tools/handle_doc_parsing.py::_parse_one_shim` | Mode A 는 SFT 전용 (로컬 pre-parsed JSON + sft_pipeline selector). master 에는 두 경로 모두 없음. |
| 3 | `mm_docqa` 모드 + `visual_tools` / `pdf_tools` / `pptx_tools` / `docx_tools` / `hwpx_tools` / `xlsx_tools` 패키지 + `analyze_visual`, `get_visuals`, `<ext>_page_layout` 도구 | `exaone/{visual_tools,pdf_tools,pptx_tools,docx_tools,hwpx_tools,xlsx_tools}/` (ir-shim), `qa_modes.py::mm_docqa` (ir-shim) | Multimodal QA 모드. 로컬 OCR/VLM 스택에 의존하며, 이는 SFT 환경에서만 실제 동작 가능. |
| 4 | `exaone/sft_gen/` 패키지 전체: Dev Files API uploader, build_dataset CLI, PA-RAG query generator, transform_to_sft, shim/{pdf_index,selector_client}, batch_runner_pool, multi-host runner | `exaone/sft_gen/` (ir-shim 전용), `exaone/batch_runner_pool.py`, `exaone/batch_runner.py` SFT prelude, `configs/hosts*.yaml` | SFT 데이터 생성 파이프라인. master 에는 없으며 cherry-pick 대상도 아님. |
| 5 | v19 chat-template adapter (Qwen3 empty-think 버그 우회) | `exaone/v19_completions_adapter.py`, `configs/chat_templates/qwen3_fixed_v19.jinja`, `exaone/agent.py::_create_request_openai_client` override, `_disable_streaming = True` | empty-think poisoning 버그는 upstream Qwen3 chat_template 를 쓰는 SFT vLLM 에서만 발현. master 배포는 서버 측 fix 사용. |
| 6 | `{language}` / `{cur_date}` placeholder 치환 + `ExaoneAgent.__init__` 의 `language` kwarg | `exaone/agent.py::_format_prompt_placeholders` (ir-shim), `exaone/prompts/style/docqa.txt` / `identities/docqa.txt` (ir-shim 사본) | SFT 배치는 row 별로 하나의 언어를 고정해야 함. production master 는 사용자 질의 언어를 그대로 따라감. 저장되는 trajectory 에는 고정값이 박히지 않아 distill 데이터는 언어 중립. |
| 7 | mm_docqa 측 auxiliary writer (`write_vlm_analyze_log`, `write_vlm_get_visuals_log`, `write_vlm_ocr_log`) | `exaone/auxiliary_tracer.py` 236 라인 이후 (ir-shim 전용) | Visual tool 들이 자체 aux LLM 호출을 발화. trace 파일 shape 은 나머지와 동일. 1-235 라인은 master 와 byte-identical. |

## 3. 아직 처리해야 할 항목

> **상태: [아직 적용 안 됨 — 처리 필요]**
> 아래 항목들은 현재 코드에 반영되지 않은 상태. 각 소절의 도입부에
> 적힌 시점(MR 전 / 선택적)까지 처리할 것.

### 3.1 `master` 의 upstream AGENTS.md / test_rule.md 위반

> **처리 시점**: MR 전 반드시. 현재 master 의 단위/스모크 테스트는 작성되지 않은 상태.

| 심각도 | 룰 | 부족한 것 | 권장 fix |
|---|---|---|---|
| CRITICAL | `test_rule.md` "MR 전 테스트 원칙 — 1차 unit test 작성" | `exaone/docqa_tools/`, `exaone/parsing_tools/`, `exaone/auxiliary_tracer.py::write_rd_extract_log`, `exaone/qa_modes.py::docqa,taskbot`, `exaone/tools.py::_register_docqa_and_parsing_tools` 등 신규 모듈 13개에 매칭되는 `tests/exaone/unit/test_*.py` 없음. | audit 에 열거된 대로 unit test 추가. 기존 `test_qa_modes.py` / `test_tools_register.py` 패턴 따라가고, IR / parser HTTP 는 mock. |
| CRITICAL | `test_rule.md` smoke trigger | (a) `qa_modes` / `toolset` 변경 → `test_agent_init.py` smoke trigger 발화; (b) 신규 `auxiliary_rd_extract_*.json` family → `test_web_extract.py` 패턴 smoke trigger 발화. 매칭되는 smoke test 없음. | `tests/exaone/smoke/test_agent_init_docqa.py`, `..._taskbot.py`, `test_rd_extract.py` 추가. CI 에 `EXAONE_BASE_URL` 가 없으면 `test_rule.md` L11-12 에 따라 PR body 에 skip 사유 명시. |
| MEDIUM | AGENTS.md §"Plugin rule" — 코어 파일 무수정 | 준수 (`run_agent.py`, `cli.py`, `gateway/run.py`, `hermes_cli/main.py`, `tools/`, `toolsets.py`, `model_tools.py` 수정 0건). | — |

### 3.2 master diff 내 스타일 / 구조 결함

> **처리 시점**: MR 전 정리 권장. 일부는 처리됨 (아래 status 칼럼 참고).

룰 위반은 아니지만 LG 리뷰어 눈에 띌 내부 sloppy 한 부분.

- **프롬프트 ↔ 스키마 drift**:
  - ⏳ `prompts/tools/ReadFullDocument.txt` 는 `goal` 을 optional 이라 설명하고 `max_chars` 가 존재한다고 말하지만, 스키마는 `goal` 을 required 로 두고 `max_chars` 는 없음.
  - ✅ `prompts/tools/doc_search.txt` 의 `selector_score` 언급은 lgair-style 스키마 도입 commit 에서 정리됨.
  - ✅ `prompts/tools/list_documents.txt` 는 idx + parsed flag 형식으로 전체 재작성 (find_documents/parse_web_and_doc commit 사이클).
  - ⏳ `prompts/tools/ReadFullDocument.txt` 의 `search(source='doc')` 언급 미정리.
  - ✅ `prompts/tools/find_documents.txt` 는 파일 자체가 제거됨 (find_documents 도구 삭제).
- **`prompts/tools/*.txt` 의 heading 비일관**: ✅ `doc_search.txt`, `list_documents.txt`, `parse_web_and_doc.txt` 는 `# Tool:` 로 통일. 나머지 (`ReadFullDocument.txt`, `get_document_chunks.txt`) 는 아직 `### Tool:` 상태 — 후속 정리 필요.
- **6개 docqa handler 간 envelope shape 비일관** — `handle_doc_search.py` 만 `success: True` 와 `data.doc` wrapper 를 갖고, 나머지는 `{"tool_name": ..., "results": [...]}` 사용. 하나의 skeleton 으로 통일.
- **Type hint 혼용**: `handle_read_full_document.py` 는 `Optional[X]` / `Dict[X, Y]` / `Tuple[…]` 사용, 나머지 신규 파일은 `X | None` / `dict[X, Y]` / `tuple[…]`. `| None` 쪽으로 정렬.
- **`_extractor_prompts.py` 에 `from __future__ import annotations` 빠짐**. 추가.
- **Threading import**: `auxiliary_tracer.py` 가 `__import__("threading").Lock()` 인라인 사용. `import threading` 을 파일 상단으로.
- **Box-drawing divider**: `_ir_client.py` 가 Unicode `# ─── … ───` 섹션 헤더 사용. upload 는 plain `# === … ===` 또는 빈 줄 + 짧은 코멘트. 변환.

### 3.3 ir-shim 의 7가지 합법 사유로 정당화되지 않는 drift

> **상태: 부분 처리됨.** 아래 표의 status 칼럼 참고.
> 처리 시점: 미처리분은 다음 ir-shim 작업 사이클에. master 에는 영향 없음.

| Status | 심각도 | Drift | 처리 내역 / 해결 |
|---|---|---|---|
| ~~SKIP~~ | — | `.gitignore` 의 `.harness/`, `.worktrees/`, `docs/active` 블록을 master 가 가지고 ir-shim 이 없음. | drift 로 다루지 않음. `.harness/` 는 master 운영에 필요한 것이 아니라 우리 워크트리 / harness 인프라용 로컬 메타데이터. 양 브랜치 동기화 대상 아님. |
| ~~DROP~~ | — | 일부 ir-shim handler 의 docstring 에서 `## Document flow policy (background)` 섹션 누락. | drift 로 다루지 않음. 진짜 기준은 **shared 파일들의 byte-identity** (`_policy.md` "Shared logic files" 표에 명시된 4개) — 그것만 유지되면 됨. docstring 내 backreference 는 navigation 도움일 뿐 핵심 계약이 아님. |
| ✅ DONE | HIGH | ir-shim `prompts/tools/doc_parsing.txt` 가 handler 가 반환하지 않는 `file_id` 출력 필드를 광고 → idx-only invariant 위반. | commit 에서 출력 설명을 실제 envelope 필드 (`document_idx`, `filename`, `extension`, `page_count`, `char_count`, `status`) 로 정확히 재작성. 마지막 문장에 "fids are internal bookkeeping and never appear in the envelope" 라고 idx-only invariant 를 모델에게 명시. heading 도 `# Tool:` (upload 컨벤션) 으로 정렬. |
| ✅ DONE | HIGH | ir-shim 의 `taskbot` 모드가 `docqa` identity / style 프롬프트를 재사용. docqa 스타일은 모델에게 `web_search` fallback 을 명시적으로 지시하지만 taskbot 에는 web 도구가 없어 모순. | commit 에서 `prompts/identities/taskbot.txt` + `prompts/style/taskbot.txt` 신규 작성. master taskbot prompt 와 동일한 정신("External knowledge sources are intentionally unavailable") 으로 작성하되 idx-only 호출 예시 + `{current_date}` placeholder + ir-shim 스타일에 맞춤. web_search / web_extract 언급 0건. `qa_modes.py` 의 taskbot 도 `identity_name="taskbot"`, `style_name="taskbot"` 으로 변경. <br><br> **master taskbot 과의 차이 한눈에**: <br>① 호출 예시: master `doc_search(queries, document_file_ids)` ↔ ir-shim `doc_search(queries, document_idx)` (idx-only 정책). <br>② placeholder: master 없음 ↔ ir-shim `{current_date}` (SFT 배치 일관성). <br>③ "do not invent file_ids or pages" ↔ "do not invent `document_idx` values or page numbers" (식별자 명칭). <br>그 외(strict TASKBOT 정체성, web 차단, 인용 룰)는 동일. |
| ⏳ PENDING | HIGH | ir-shim 의 `taskbot` toolset 이 프롬프트 커버 없이 `pdf_tools, pptx_tools, docx_tools, hwpx_tools, xlsx_tools` 를 번들. | 사용자 지시로 이번 사이클에서는 유지. 다음 사이클에서 `qa_modes.py::taskbot.toolset` 에서 제거하거나, taskbot 프롬프트를 확장해 page-layout 도구 사용법을 모델에 학습시킬 것. |

### 3.4 master 가 흡수하면 좋을 ir-shim 측 개선

> **처리 시점**: 선택적. blocker 아님 — 기회 될 때 port.
> 현재 master 에는 미반영. ir-shim 측에는 이미 적용되어 있음.

SFT 전용이 아닌 ir-shim 측 일반적 품질 개선들:

- **`tools/web_tools.py` 의 BRAVE_KEYS rotation** — random start offset + auth-error backoff + key-pool 순환. 동시 worker 가 많은 master 배포에도 동일하게 유용.
- **`exaone/config.py` 의 vendor sampling preset** — Qwen3 family 기본 sampling 파라미터. 이미 `EXAONE_AUTO_SAMPLING=1` 로 gating 되어 cherry-pick 안전.
- **`exaone/agent.py` 의 `enable_thinking` pin** — 서버 template 기본값 차이를 흡수해 reasoning 모드를 고정. master 가 여러 vLLM 배포를 타깃할 가능성이 있다면 의미 있음.

위 셋 모두 blocker 아님 — required sync 가 아니라 기회가 되면 port 하는 항목으로 다룰 것.
