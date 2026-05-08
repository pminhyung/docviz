#!/usr/bin/env python3
"""
agent API 최소 예시 코드

다양한 사용 케이스별 최소한의 코드 예시입니다.
각 함수는 독립적으로 실행 가능합니다.

사용 전 준비:
    1. API 서버 실행 (run_server.sh 참고)
    2. API_KEY 값을 실제 키로 교체
"""
import requests

# ==============================================================================
# 설정 - 반드시 실제 값으로 교체하세요
# ==============================================================================

API_URL = "http://10.4.43.13:9024"
API_KEY = "your-openai-api-key-here"  # 필수: OpenAI API 키 (기본 모델 gpt-5.2)


# ==============================================================================
# 케이스 1: 가장 기본적인 요청 (필수 파라미터만)
# ==============================================================================

def case1_minimal():
    """최소 요청 - 문서 경로, 질문, API 키만 전달"""
    response = requests.post(f"{API_URL}/v2/run", json={
        "doc_json_path": "/path/to/document.json",
        "user_query": "이 문서를 요약해주세요",
        "reasoner_api_key": API_KEY,
    })
    result = response.json()
    print(result["final_answer"])


# ==============================================================================
# 케이스 2: 한국어 응답
# ==============================================================================

def case2_korean():
    """한국어로 응답 받기"""
    response = requests.post(f"{API_URL}/v2/run", json={
        "doc_json_path": "/path/to/document.json",
        "user_query": "목표주가를 알려주세요",
        "reasoner_api_key": API_KEY,
        "lang": "ko",  # "ko" 또는 "en"
    })
    result = response.json()
    print(result["final_answer"])


# ==============================================================================
# 케이스 3: VL(이미지 분석) 모드
# ==============================================================================

def case3_vl_mode():
    """이미지 분석이 필요한 경우 VL 모드 사용"""
    response = requests.post(f"{API_URL}/v2/run", json={
        "doc_json_path": "/path/to/document.json",
        "doc_image_dir": "/path/to/images/",  # 이미지 폴더
        "user_query": "차트를 분석해주세요",
        "reasoner_api_key": API_KEY,
        "reasoner_type": "vl",  # "llm"(기본) 또는 "vl"(이미지 입력 지원)
    })
    result = response.json()
    print(result["final_answer"])


# ==============================================================================
# 케이스 4: OpenAI GPT 모델 사용
# ==============================================================================

def case4_openai():
    """다른 OpenAI 모델 사용 (기본: gpt-5.2, 변경 예: gpt-4o)"""
    response = requests.post(f"{API_URL}/v2/run", json={
        "doc_json_path": "/path/to/document.json",
        "user_query": "분석해주세요",
        "reasoner_api_key": "sk-your-openai-api-key",  # OpenAI API 키
        "reasoner_model_name": "gpt-4o",  # 기본 gpt-5.2 대신 다른 모델 사용
    })
    result = response.json()
    print(result["final_answer"])


# ==============================================================================
# 케이스 5: 커스텀 도구 사용
# ==============================================================================

def case5_custom_tools():
    """커스텀 도구를 추가하여 사용"""
    response = requests.post(f"{API_URL}/v2/run", json={
        "doc_json_path": "/path/to/document.json",
        "user_query": "차트를 분석해주세요",
        "reasoner_api_key": API_KEY,
        "custom_tools_path": "/path/to/my_tools.py",  # 커스텀 도구 파일
        "tool_secrets": {  # 커스텀 도구에 전달할 비밀값
            "vl_api_key": "sk_xxx",
        },
    })
    result = response.json()
    print(result["final_answer"])


# ==============================================================================
# 케이스 6: 배치 처리 (세션 사용)
# ==============================================================================

def case6_batch():
    """여러 문서를 처리하고 결과를 누적하여 GCS 업로드"""

    SESSION_ID = "my_batch_001"

    # 1. 여러 요청 실행 (같은 session_id로 결과 누적)
    documents = [
        {"path": "/path/to/doc1.json", "query": "문서1 요약"},
        {"path": "/path/to/doc2.json", "query": "문서2 요약"},
    ]

    for doc in documents:
        response = requests.post(f"{API_URL}/v2/run", json={
            "doc_json_path": doc["path"],
            "user_query": doc["query"],
            "reasoner_api_key": API_KEY,
            "session_id": SESSION_ID,  # 동일 세션으로 누적
        })
        print(f"누적 샘플: {response.json()['session_sample_count']}")

    # 2. 세션 종료 및 GCS 업로드
    final = requests.post(f"{API_URL}/v2/finalize_session", json={
        "session_id": SESSION_ID
    })
    print(f"GCS 경로: {final.json()['gcs_path']}")


# ==============================================================================
# 케이스 7: 응답 상세 정보 확인
# ==============================================================================

def case7_detailed_response():
    """응답의 상세 정보 확인"""
    response = requests.post(f"{API_URL}/v2/run", json={
        "doc_json_path": "/path/to/document.json",
        "user_query": "분석해주세요",
        "reasoner_api_key": API_KEY,
        "return_trace": True,  # 추론 과정 포함
    })

    result = response.json()

    # 기본 정보
    print(f"성공 여부: {result['success']}")
    print(f"총 토큰: {result['total_tokens']}")
    print(f"처리 시간: {result['total_duration_seconds']}초")
    print(f"스텝 수: {result['num_steps']}")

    # 스텝별 정보
    print("\n[스텝 상세]")
    for step in result["steps_reasoning"]:
        action = step.get("action", {}).get("name", "-")
        print(f"  {step['step_number']}. {step['step_name']} ({action})")

    # 최종 답변
    print(f"\n[답변]\n{result['final_answer']}")


# ==============================================================================
# 메인 실행
# ==============================================================================

if __name__ == "__main__":
    import sys

    cases = {
        "1": ("기본 요청", case1_minimal),
        "2": ("한국어 응답", case2_korean),
        "3": ("VL 모드", case3_vl_mode),
        "4": ("OpenAI 모델", case4_openai),
        "5": ("커스텀 도구", case5_custom_tools),
        "6": ("배치 처리", case6_batch),
        "7": ("상세 응답", case7_detailed_response),
    }

    if len(sys.argv) < 2:
        print("사용법: python minimal_examples.py <케이스번호>")
        print("\n케이스:")
        for num, (name, _) in cases.items():
            print(f"  {num}: {name}")
        sys.exit(0)

    case_num = sys.argv[1]
    if case_num in cases:
        name, func = cases[case_num]
        print(f"실행: {name}")
        func()
    else:
        print(f"알 수 없는 케이스: {case_num}")
