# SFT Data Guide

## 0. 전제: 데이터 스키마

각 record는 다음 구조다. 모든 검사는 이 스키마 위에서 수행한다.
- conversations system은 system_blocks 내용을 기반으로 붙여서 만들어주시면 됩니다. (custom, memory에 들어가는 태그를 conversations system content 추가해주시면 되겠습니다)

```json
{
  "id": "<query_id>",
  "system_blocks": {
    "identity": "...",
    "style": "...",
    "tool_list": "...",
    "custom": "",
    "memory": ""
  },
  "available_tools": ["web_search", "web_extract", "code_tool"], (optional)
  "tools": [
    { "type": "function", "function": { "name": "web_search", "description": "...", "parameters": {...} } },
    ...
  ],
  "conversations": [
    { "role": "system",    "content": "<full system prompt>", "loss_masking": true },
    { "role": "user",      "content": "<user query>",        "loss_masking": true },
    { "role": "assistant", "reasoning_content": "...",
                           "content": "",
                           "tool_calls": [{ "type": "function",
                                            "function": { "name": "web_search",
                                                          "arguments": { "queries": [...] } } }],
                           "loss_masking": false },
    { "role": "tool",      "tool_call_id": "<tcid>",
                           "name": "web_search",
                           "content": "<JSON envelope string>",
                           "loss_masking": true },
    { "role": "assistant", "reasoning_content": "...",
                           "content": "<final answer with [tcid.idx] citations>",
                           "loss_masking": false }
  ]
}
```

용어:
- **last_user_index** = `max(i for i,m in enumerate(conversations) if m.role == "user")`
- **history turns** = `conversations[: last_user_index + 1]` — multi-turn 데이터에서 마지막 user 이전 영역
- **rollout turns** = `conversations[last_user_index + 1 :]` — 실제 모델 rollout (학습 target)

---

## 1. Loss masking

`loss_masking == True` = 해당 turn 의 loss를 **마스킹** (학습 안 함, context only)
`loss_masking == False` = 학습 target (loss 계산)

### 1.1 Single-turn trajectory

user 1번 + assistant 여러 번 (tool call + final). 모든 assistant turn 이 학습 대상.

**기대 패턴**

| index | role | loss_masking |
| --- | --- | --- |
| 0 | system | True |
| 1 | user | True |
| 2 | assistant (tool_call) | **False** |
| 3 | tool | True |
| 4 | assistant (final) | **False** |

**위반 예시**
```json
// ass turn에 loss=True (학습에서 빠짐 — 잘못된 마스킹)
{"role": "assistant", "content": "...", "loss_masking": true}
```

### 1.2 Multi-turn trajectory

user 메시지가 2개 이상. 마지막 user 이전은 **dataset 제공 history**, 이후만 모델 rollout.

**기대 패턴**

| index | role | loss_masking | 비고 |
| --- | --- | --- | --- |
| 0 | system | True |  |
| 1 | user | True | (history) |
| 2 | assistant | **True** | history ass (학습 안 함) |
| 3 | user | True | (history) |
| 4 | assistant | True | history ass |
| 5 | user | True | **last_user** |
| 6 | assistant (tool_call) | **False** | rollout |
| 7 | tool | True |  |
| 8 | assistant (final) | **False** | rollout |

**위반 예시**
```json
// history 안의 ass가 loss=False (history 를 학습 target으로 잘못 표시)
{"role": "assistant", "content": "<history reply>", "loss_masking": false}
// 이건 index 2 또는 4 위치, 즉 last_user 이전
```

### 1.3 Aux task trajectory

- **TBD** - **샘플이 수집된 뒤에 실제 분포·shape 보고 필터링 가이드를 정한다.** 임시 작성된 초안은 문서 끝 **부록 A** 참조 (web_extract LLM summary / compaction case A·B·C 예시 포함).
- **Web Extract**
    - 각 run 폴더안에
        - auxiliary_web_extract_{idx}.json 파일 취합 후 전달
- **Compaction**
    - Hold → 1차 데이터 취합에는 전달 안해주셔도됩니다.
        - 추후 가이드 드리겠습니다.
- **Finalizer (TBD)**

---

## 2. Interleaved Thinking

멀티턴 history 가 누적될 때, **이전 user 턴들에 대한 ass response 는 `reasoning_content` 없이** 저장돼야 한다.

### 기대 패턴

```json
// last_user 이전 — history 영역의 ass turn
{
  "role": "assistant",
  "reasoning_content": "",         // 또는 키 자체 없음
  "content": "<final answer text>",
  // history는 final answer만
  "loss_masking": true
}

// last_user 이후 — rollout 영역의 ass turn
{
  "role": "assistant",
  "reasoning_content": "<non-empty reasoning>",  // rollout 은 reasoning 보유
  "content": "<final answer text>",
  "loss_masking": false
}
```

### 위반 예시
```json
// history (loss=true) 인데 reasoning_content 가 채워짐 → mismatch
{
  "role": "assistant",
  "reasoning_content": "Let me think about this...",
  "content": "이전 답변 텍스트",
  "loss_masking": true
}
```

---

## 3. Tool Call

### 3.1 tools에 없는 tool 참조

assistant turn 의 모든 `tool_calls[*].function.name` 은 record 의 `tools[*].function.name` 집합 안에 있어야 한다.

**기대**: 호출 가능한 tool name = `{"web_search", "web_extract", "code_tool"}` 일 때, 그 외 호출 없음.

**위반 예시**
```json
"tools": [
  {"function": {"name": "web_search", ...}},
  {"function": {"name": "web_extract", ...}}
],
"conversations": [
  ...,
  {
    "role": "assistant",
    "tool_calls": [{"function": {"name": "calculator", "arguments": {...}}}],
    "loss_masking": false
  }
]
```
→ `calculator` 가 `tools` 에 정의되지 않았으므로 위반.

### 3.2 Tool result 가 empty

tool 메시지 content 를 JSON parse 한 envelope의 `results` 가 빈 경우, 또는 results 안 모든 item 이 의미 있는 데이터를 못 담은 경우.

**검사 패턴 (tool name 별)**

| tool name | empty 판정 기준 |
| --- | --- |
| `web_search` | `results == []` 또는 모든 item에 site/snippet/url 누락 |
| `web_extract` | `results == []` 또는 모든 item에 `error` 필드 / `contents == ""` |
| `code_tool` | `results == []` 또는 모든 item이 `stdout == "" && stderr == ""` (둘 다 비어있음) |

**위반 예시**
```json
// web_search empty
{
  "role": "tool",
  "name": "web_search",
  "content": "{\"results\": []}"
}

// web_extract 전체 item error
{
  "role": "tool",
  "name": "web_extract",
  "content": "{\"results\": [{\"Index\": \"abc.0\", \"url\": \"...\", \"error\": \"Blocked: private network\"}]}"
}
```

> **담당자 처리 가이드**:
> 예외처리가 필요하면 **tool name 기준으로 분기**해서 확인할 수 있도록 분류한다.
> 예) web_search empty 는 query 품질 문제 혹은 api call err일 수 있기 때문에 empty result는 drop을 원칙으로 가져감.

### 3.3 Invalid args (schema 위반)

tool_call 의 `arguments` 가 해당 tool 의 schema (`parameters`) 와 일치하지 않으면 tool dispatch 단계에서 validation error → tool result 가 `is_error: true` 또는 빈 결과로 잡힘. 학습 데이터로 들어가면 모델이 "잘못된 args 패턴 → 정상 진행"을 학습하게 되므로 차단해야 함.

**검사 기준**

| 항목 | 위반 |
| --- | --- |
| 누락 | schema.parameters.required 의 일부가 args에 없음 |
| 타입 불일치 | schema 가 `array` 인데 args 는 `string` 등 |
| Unknown 키 (additionalProperties=false) | schema 의 properties 키 외 추가 키 |

**실제 schema 예시** (`web_search`):
```json
{
  "type": "function",
  "function": {
    "name": "web_search",
    "parameters": {
      "type": "object",
      "properties": {
        "queries": { "type": "array", "items": { "type": "string" } }
      },
      "required": ["queries"]
    }
  }
}
```

**위반 예시 (`web_search`)**
```json
// 1) Required 누락 — queries 없음
{ "function": { "name": "web_search", "arguments": { "language": "ko" } } }

// 2) 타입 불일치 — queries 가 array 가 아닌 string
{ "function": { "name": "web_search", "arguments": { "queries": "맥심 블랙커피" } } }

// 3) Unknown 키 — schema에 없는 language/num_results
{ "function": { "name": "web_search",
                "arguments": { "queries": ["맥심 블랙커피"], "language": "ko", "num_results": 10 } } }
```

**위반 예시 (`code_tool`)**
```json
// code_tool schema: required ["code"], properties = {"code": {"type": "string"}}
// 1) Required 누락 — code 없음
{ "function": { "name": "code_tool", "arguments": { "src": "print(1)" } } }

// 2) 타입 불일치 — code 가 string 이 아닌 array
{ "function": { "name": "code_tool", "arguments": { "code": ["print(1)", "print(2)"] } } }
```

### 3.4 한 trajectory 안 같은 tcid 중복 금지

**기대**: 한 record 안 모든 tool 메시지의 `tool_call_id` 가 distinct.

**위반 예시**
```json
"conversations": [
  ...,
  {"role": "assistant", "tool_calls": [{"function": {"name": "web_search", ...}}]},
  {"role": "tool", "tool_call_id": "hbt598", "name": "web_search", "content": "..."},
  {"role": "assistant", "tool_calls": [{"function": {"name": "web_search", ...}}]},
  {"role": "tool", "tool_call_id": "hbt598", "name": "web_search", "content": "..."}  // ← 중복
]
```

---

## 4. Citation

citation 형식은 `[<tool_call_id>.<idx>]`. 예: `[hbt598.0]`, `[clw981.4]`.

### 4.1 Hallucination — tcid.idx 가 실제 tool result 안에 없음

rollout 영역의 모든 ass turn (`content` + `reasoning_content`) 에서 추출한 모든 `[tcid.idx]` 가, 같은 trajectory 안 web_search / web_extract / doc tool result 의 `Index` 집합 subset 이어야 한다.

> 그 외 citation 대상이 될수있는 tool이 있으면 valid_set에 추가 필요

**기대**:
```
cited_set ⊆ valid_set
  where
    cited_set  = ∪(rollout ass turn 에서 [tcid.idx] 추출 — 코드 영역 제외)
    valid_set  = ∪(prior tool result envelope.results[*].Index)
```

### 코드 영역 제외 (false positive 회피)

`[a.b]` 형식은 코드 안에서도 자연스럽게 등장 (예: Python list, indexing, list comprehension). citation regex 적용 **전에** 다음 영역을 마스킹한다.

**제외 대상**

| 영역 | 마스킹 패턴 | 예시 |
| --- | --- | --- |
| Fenced code block | ` ```...``` ` (지정 언어 포함) | ` ```python\narr = [a.b for a in xs]\n``` ` |
| Inline code span | `` `code` `` | `` `df[col.name]` `` |

**구현 흐름**
1. 원본 text 에서 위 영역을 공백 (또는 임의 마스킹 토큰) 으로 치환
2. 남은 text 에 citation regex `\[([A-Za-z0-9_]+\.\d+)\]` 적용
3. 매칭된 cite_set 으로 hallucination 검사

**False positive 예시 (코드 영역 마스킹 안 하면 잘못 탐지)**
````markdown
사용 예시:
```python
data = [user.id for user in users]   ← [user.id] 가 citation 으로 잘못 잡힘
```
````

**True positive 예시 (코드 영역 제외 후에도 살아남는 위반)**
```markdown
검색 결과에 따르면 정답은 X 입니다[xyz999.0].
```
→ 코드 밖이고, `xyz999.0` 이 valid_set 에 없으면 hallucination.

> **참고**: style prompt 가 markdown link `[text](url)` 를 금지하고 있으므로, citation 패턴이 `(url)` 직후에 등장하면 그 자체가 별도 style 위반이지만 citation 검사에서는 일단 매칭 처리 (정상 citation 다음 우연히 괄호가 올 가능성 무시 가능).

**위반 예시**
```json
// tool result에 hbt598.0 ~ hbt598.9 만 존재
// 하지만 ass 답변에서:
{
  "role": "assistant",
  "content": "정답입니다[hbt598.0][hbt598.25].",  // ← hbt598.25 hallucinated
  "loss_masking": false
}
```
```json
// tcid 자체가 invent된 경우
{
  "role": "assistant",
  "content": "...[xyz999.0]...",  // ← tool result에 xyz999.* 없음
  "loss_masking": false
}
```

### 4.2 Invalid citation format

`[<tcid>.<idx>]` 외 다른 형식의 brackets은 위반.

**허용되는 chaining**: 연속된 bracket, 예 `[hbt598.0][clw981.3]`.

**위반 예시**
```json
// comma로 묶음
"content": "...[ref1, ref2]..."
// range 표기
"content": "...[ref1-10]..."
// 한 bracket 안에 여러 source
"content": "...[hbt598.0, clw981.3]..."
// tcid 없이 숫자만
"content": "...본문[1]..."
// 한글 prefix
"content": "...[참고1]..."
```

**검사 정규식 예시**:
- 허용 패턴: `\[([A-Za-z0-9_]+\.\d+)\]`
- 비허용 패턴 (별도 flag): `\[[^\]]*[,\-][^\]]*\]` (bracket 안 콤마 또는 hyphen)

---

## 5. Too Long

> **TBD (정확 임계치)** — 너무 긴 출력은 모델이 stuck / 무한 반복 / 큰 dump (이미지 base64 등) 한 경우가 많음. **정확한 cap 값은 실제 학습 데이터 분포 보고 확정**한다.

### 5.1 Thinking (reasoning_content)

단일 ass turn 의 `reasoning_content` 길이가 `CAP_THINKING` 초과 시 해당 record 드랍.

EMPTY Reasoning Content 관련 정책
- 1차 학습 정책: assistant 턴의 `reasoning_content` 는 필수적으로 채워져있어야함.
    - (추후 변경 여지는 있음)

### 5.2 Tool result

단일 tool 메시지 `content` (envelope JSON 포함 길이) 가 `CAP_TOOL_RESULT` 초과 시 해당 record 드랍.

---

## 6. Structural Validity

대화 구조 자체가 valid 한지.

### 6.1 Role sequence valid

valid 시퀀스: **`system → user → (assistant ↔ tool)* → assistant`**

세부 규칙:
- `system` 메시지는 최대 1개, 항상 index 0.
- `user` 와 `assistant` 가 교대로 등장 (multi-turn 의 경우 user→ass→user→ass→ ...).
- `assistant` 가 `tool_calls` 를 보유하면, 직후에 같은 `tool_call_id` 를 가진 `tool` 메시지가 와야 함 (1:1 매칭, 동일 ass turn 의 모든 tool_call 각각에 대해).

**위반 예시**
```json
// tool 이 ass.tool_call 없이 등장
[
  {"role": "system"},
  {"role": "user"},
  {"role": "tool", "tool_call_id": "abc", "content": "..."}   // ← 잘못
]

// assistant 연속 (history 가 아닌 rollout 영역에서)
[
  ...,
  {"role": "user", "...": "..."},
  {"role": "assistant", "content": "..."},
  {"role": "assistant", "content": "..."}   // ← tool 없이 두 번 연속
]
```

### 6.2 마지막 메시지가 ass final answer

`conversations[-1]` 은:
- `role == "assistant"`
- `tool_calls` 가 **없음** (또는 빈 리스트)
- `content` 가 **non-empty**

**위반 예시**
```json
// 마지막이 tool 메시지로 끝남 (final answer 누락)
"conversations": [
  ...,
  {"role": "tool", "name": "web_search", "content": "..."}
]

// 마지막 ass 가 tool_call 만 있고 content 비어있음 (final answer 못 만든 상태)
"conversations": [
  ...,
  {
    "role": "assistant",
    "reasoning_content": "...",
    "content": "",
    "tool_calls": [{"function": {"name": "web_search", ...}}],
    "loss_masking": false
  }
]
```

---

## 부록 A — Aux task trajectory (TBD, 샘플 수집 후 확정)

> 본 부록은 aux task (web_extract LLM summary, context compaction) 발생 trajectory 의 정합성 규칙 **초안**이다. 현재 preprocess 파이프라인은 이런 trajectory 를 모두 `drop:has_aux_files` 로 제외 중이며, 실제 샘플을 모아 shape·빈도·실패 패턴을 본 뒤 본문(1.3) 으로 승격할 예정. 코드 동작은 `agent/context_compressor.py:compress`, `exaone/compaction_tracer.py` 기준.

### A.1 파생 instance 종류

aux task 가 발생한 main trajectory 에서 파생 가능한 학습 instance 종류:
- (a) main rollout 본체 — 기존 single/multi-turn 규칙대로 loss masking
- (b) aux LLM 호출 자체의 input → output 학습 instance — trace 파일 (`_aux-*_compaction*.json` 또는 `_step1-*_compaction*.json` triplet) 에서 별도 ETL 로 추출

### A.2 web_extract LLM summary

main trajectory 안에서 web_extract 가 35K~100K char 페이지를 만나면 내부적으로 aux LLM 을 호출하여 요약본을 만들고, **그 요약본만 main tool result 의 `contents` 로 반환**한다. aux 호출의 raw input → summary output 자체는 main conversation 에 들어가지 않고 trace 파일 (`NN_step_aux-web_extract_*_compaction.json` 트리플렛) 로만 남는다.

```json
// (a) main trajectory — aux 호출 흔적은 안 보이고 결과만 contents 에
{
  "id": "<qid>",
  "conversations": [
    { "role": "system",    "content": "...", "loss_masking": true },
    { "role": "user",      "content": "스테이크 소스 만드는 법 알려줘", "loss_masking": true },
    {
      "role": "assistant", "reasoning_content": "검색 후 본문 확인이 필요",
      "content": "", "loss_masking": false,
      "tool_calls": [{ "function": { "name": "web_extract",
                                     "arguments": { "urls": ["https://..."] } } }]
    },
    {
      "role": "tool", "tool_call_id": "pes202", "name": "web_extract",
      // ↓ summarized: true — aux LLM 으로 압축된 결과
      "content": "{\"results\": [{\"Index\": \"pes202.0\", \"url\": \"...\", \"contents\": \"<요약된 본문>\", \"summarized\": true}]}",
      "loss_masking": true
    },
    { "role": "assistant", "reasoning_content": "...", "content": "최종 답변[pes202.0]", "loss_masking": false }
  ]
}

// (b) 별도 ETL 로 trace 파일에서 추출한 aux 학습 instance
{
  "id": "<qid>_aux_web_extract_1",
  "conversations": [
    { "role": "system",    "content": "<aux summarizer instruction: 본문을 35K 이내로 요약하라>", "loss_masking": true },
    { "role": "user",      "content": "<raw markdown 70K char 원문>", "loss_masking": true },
    { "role": "assistant", "content": "<요약된 본문 (위 main tool result 의 contents 와 동일)>", "loss_masking": false }
  ]
}
```

**검사 포인트 (초안)**
- main trajectory: `tool` 메시지의 `results[*].summarized == true` 면 aux 호출이 발생한 것 — 이 trajectory 가 학습 데이터에 있다면 일관성 cross-check.
- aux instance (별도 추출): system/user = `loss_masking: true`, assistant 결과 = `loss_masking: false`.
- aux instance 의 assistant.content 와 main trajectory tool result 의 `results[*].contents` 가 일치해야 함.

### A.3 Compaction trajectory

context 가 임계치를 넘으면 main loop 이전 turns 를 한 단락 summary 로 압축하고, 그 summary 를 **`user` 또는 `assistant` 역할** 의 메시지로 삽입한다 (consecutive same-role 회피를 위해 동적 선택, `agent/context_compressor.py:1517-1542`). 양쪽 모두 collision 이면 첫 tail 메시지의 content 앞에 prepend.

다음 3종 학습 instance 가 파생 가능:
1. **Pre-compaction traj** — 압축 trigger 시점까지의 정상 rollout
2. **Compaction sample (aux instance)** — 이전 conversation 을 summary 로 압축한 aux LLM 호출 (trace 파일에서 별도 ETL)
3. **Post-compaction traj** — 압축 summary 가 삽입된 채 continued rollout

**(1) Pre-compaction trajectory**
```json
{
  "id": "<qid>_pre_compaction",
  "conversations": [
    { "role": "system", "content": "...", "loss_masking": true },
    { "role": "user",   "content": "...", "loss_masking": true },
    { "role": "assistant", "reasoning_content": "...", "content": "",
      "tool_calls": [{ "function": { "name": "web_search", ... } }], "loss_masking": false },
    { "role": "tool", "tool_call_id": "t01", "name": "web_search", "content": "{...}", "loss_masking": true },
    { "role": "assistant", "reasoning_content": "...", "content": "",
      "tool_calls": [{ "function": { "name": "web_extract", ... } }], "loss_masking": false },
    { "role": "tool", "tool_call_id": "t02", "name": "web_extract", "content": "{...}", "loss_masking": true }
    // ↑ 이 직후에 context 임계치 초과 → 압축 trigger. 여기까지를 별도 학습 instance 로 보존.
  ]
}
```

**(2) Compaction sample (aux instance, trace에서 추출)**
```json
{
  "id": "<qid>_compaction_01",
  "conversations": [
    { "role": "system",    "content": "<compaction summarizer instruction>", "loss_masking": true },
    { "role": "user",      "content": "<직전 N개 turn 의 raw transcript>", "loss_masking": true },
    { "role": "assistant", "content": "<압축된 conversation summary text>", "loss_masking": false }
  ]
}
```

**(3) Post-compaction trajectory** — summary 가 main conversation 안에 인라인 삽입

`agent/context_compressor.py:compress` 가 선택한 `summary_role` 에 따라 세 가지 형태가 가능:

```json
// ── Case A: summary_role == "user" 로 삽입 (head 가 ass/tool 인 경우) ──
{
  "id": "<qid>_post_compaction",
  "conversations": [
    { "role": "system", "content": "...", "loss_masking": true },
    { "role": "user",   "content": "<원본 user query>", "loss_masking": true },
    // ── 압축으로 대체된 이전 step 영역 — 모델 생성 아님 → loss_masking=true ──
    {
      "role": "user",
      "content": "<compaction summary text>\n\n--- END OF CONTEXT SUMMARY — respond to the message below, not the summary above ---",
      "loss_masking": true
    },
    // ── 압축 이후 continued rollout — 정상 rollout 규칙 ──
    { "role": "assistant", "reasoning_content": "압축 본문 기반으로 답변 마저 생성",
      "content": "...", "tool_calls": [...], "loss_masking": false },
    { "role": "tool", "tool_call_id": "t03", "name": "web_search", "content": "{...}", "loss_masking": true },
    { "role": "assistant", "reasoning_content": "...", "content": "<final answer>", "loss_masking": false }
  ]
}
```

```json
// ── Case B: summary_role == "assistant" 로 삽입 (head 가 user/system 이고 tail 이 user 가 아닌 경우) ──
{
  "id": "<qid>_post_compaction",
  "conversations": [
    { "role": "system", "content": "...", "loss_masking": true },
    { "role": "user",   "content": "...", "loss_masking": true },
    {
      "role": "assistant",
      "content": "<compaction summary text>",
      // 모델이 생성한 게 아니라 compactor 가 만든 합성 turn → loss_masking=true
      "loss_masking": true
    },
    // 이후 continued rollout
    { "role": "tool", ..., "loss_masking": true },
    { "role": "assistant", "reasoning_content": "...", "content": "<final answer>", "loss_masking": false }
  ]
}
```

```json
// ── Case C: 양쪽 collision → 첫 tail 메시지에 prepend ──
{
  "id": "<qid>_post_compaction",
  "conversations": [
    ...,
    {
      "role": "<원래 tail 메시지의 role>",
      "content": "<compaction summary text>\n\n--- END OF CONTEXT SUMMARY — respond to the message below, not the summary above ---\n\n<원래 tail 메시지의 content>",
      "loss_masking": true
    },
    ...
  ]
}
```

> Case A/B 의 경우 삽입된 summary turn 자체가 `loss_masking: true`. Case C 는 원래 turn 의 content 가 변형됐으므로 변형된 그 turn 전체가 `loss_masking: true` (원래도 true 였을 user/tool 메시지인 경우 변화 없음, 만약 ass였다면 그 ass 는 모델이 생성한 게 아닌 합성 turn 이 되므로 true).

### A.4 검사 포인트 요약 (부록 A 전체, 초안)

| 항목 | 기대 |
| --- | --- |
| aux instance (A.2 / A.3 의 (2)) system/user | `loss_masking: true` |
| aux instance 의 assistant (요약/압축 출력) | `loss_masking: false` |
| post-compaction traj 안 compaction summary turn (Case A/B/C) | **`loss_masking: true`** |
| post-compaction traj 의 continued rollout | 정상 rollout 규칙 |
| compaction summary turn 의 role | `user` 또는 `assistant` 중 하나 (또는 tail 에 prepend) — `tool` 메시지가 아님 |
