#!/usr/bin/env python3
"""
agent API 클라이언트 예시

커스텀 Tool을 사용한 문서 분석 + 학습 데이터 생성 전체 워크플로우.

Usage:
    # 단일 쿼리
    python client_example.py \\
        --doc /path/to/doc.json \\
        --query "2페이지의 차트를 분석해주세요" \\
        --api-key your-key

    # 이미지 분석 포함
    python client_example.py \\
        --doc /path/to/doc.json \\
        --image-dir /path/to/images/ \\
        --tools /path/to/my_tools.py \\
        --query "테이블 데이터를 추출해주세요" \\
        --api-key your-key

    # 세션 누적 + GCS 업로드
    python client_example.py \\
        --doc /path/to/doc.json \\
        --query "분석해주세요" \\
        --api-key your-key \\
        --session my_batch_001 \\
        --finalize

    # 배치 처리 (JSONL 파일)
    python client_example.py \\
        --batch queries.jsonl \\
        --api-key your-key \\
        --session batch_001 \\
        --finalize

서버 시작:
    ./run_server.sh (기본 포트 9024)
"""
import os
import sys
import json
import argparse
import requests
from pathlib import Path
from typing import Optional, Dict, Any, List


API_BASE_URL = os.environ.get("DOC_AGENT_API_URL", "http://10.4.43.13:9024")


# =============================================================================
# API 호출 함수
# =============================================================================

def check_health() -> bool:
    """서버 상태 확인."""
    try:
        r = requests.get(f"{API_BASE_URL}/health", timeout=5)
        if r.status_code == 200:
            h = r.json()
            print(f"[OK] Server: {h['status']} | Version: {h['version']}")
            return True
        print(f"[ERROR] Status {r.status_code}")
        return False
    except requests.exceptions.ConnectionError:
        print(f"[ERROR] 서버에 연결할 수 없습니다: {API_BASE_URL}")
        print("        서버 시작: ./run_server.sh")
        return False


def run_query(
    doc_json_path: str,
    user_query: str,
    reasoner_api_key: str,
    doc_image_dir: Optional[str] = None,
    custom_tools_path: Optional[str] = None,
    custom_rules: Optional[str] = None,
    tool_secrets: Optional[Dict[str, str]] = None,
    lang: str = "ko",
    session_id: Optional[str] = None,
    n_steps_max: int = 10,
    reasoner_type: str = "llm",
    reasoner_model_name: Optional[str] = None,
    reasoner_base_url: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """단일 쿼리 실행."""

    body: Dict[str, Any] = {
        "doc_json_path": doc_json_path,
        "user_query": user_query,
        "reasoner_api_key": reasoner_api_key,
        "lang": lang,
        "n_steps_max": n_steps_max,
        "return_trace": True,
    }

    if doc_image_dir:
        body["doc_image_dir"] = doc_image_dir
    if custom_tools_path:
        body["custom_tools_path"] = custom_tools_path
    if custom_rules:
        body["custom_rules"] = custom_rules
    if tool_secrets:
        body["tool_secrets"] = tool_secrets
    if session_id:
        body["session_id"] = session_id
    if reasoner_type != "llm":
        body["reasoner_type"] = reasoner_type
    if reasoner_model_name:
        body["reasoner_model_name"] = reasoner_model_name
    if reasoner_base_url:
        body["reasoner_base_url"] = reasoner_base_url

    print(f"\n{'='*60}")
    print(f"Doc:   {doc_json_path}")
    print(f"Query: {user_query[:70]}{'...' if len(user_query) > 70 else ''}")
    if custom_tools_path:
        print(f"Tools: {custom_tools_path}")
    print(f"{'='*60}")

    try:
        r = requests.post(f"{API_BASE_URL}/v2/run", json=body, timeout=300)

        if r.status_code != 200:
            print(f"[ERROR] {r.status_code}: {r.text[:300]}")
            return None

        result = r.json()

        # 결과 출력
        print(f"\n[Result]")
        print(f"  Success:  {result['success']}")
        print(f"  Steps:    {result['num_steps']}")
        print(f"  Tokens:   {result['total_tokens']}")
        print(f"  Duration: {result['total_duration_seconds']:.1f}s")

        if session_id:
            print(f"  Session Samples: {result.get('session_sample_count', '-')}")

        # 사용된 도구
        tools_used = []
        for step in result.get("steps_reasoning", []):
            if step.get("action"):
                name = step["action"]["name"]
                tools_used.append(name)
                print(f"  Step {step['step_number']}: {name}")

        # 답변
        print(f"\n[Answer]")
        print("-" * 60)
        print(result.get("final_answer", ""))
        print("-" * 60)

        return result

    except requests.exceptions.Timeout:
        print("[ERROR] 타임아웃 (5분 초과)")
        return None
    except Exception as e:
        print(f"[ERROR] {e}")
        return None


def finalize_session(session_id: str) -> Optional[Dict[str, Any]]:
    """세션 종료 + GCS 업로드."""
    print(f"\n{'='*60}")
    print(f"세션 종료: {session_id}")
    print(f"{'='*60}")

    try:
        r = requests.post(
            f"{API_BASE_URL}/v2/finalize_session",
            json={"session_id": session_id},
            timeout=60,
        )

        if r.status_code == 200:
            result = r.json()
            print(f"  Session:  {result['session_id']}")
            print(f"  Samples:  {result['sample_count']}")
            print(f"  GCS Path: {result.get('gcs_path', '-')}")
            print(f"  Success:  {result['success']}")
            return result
        else:
            print(f"[ERROR] {r.text}")
            return None

    except Exception as e:
        print(f"[ERROR] {e}")
        return None


def run_batch(
    batch_path: str,
    reasoner_api_key: str,
    session_id: str,
    custom_tools_path: Optional[str] = None,
    custom_rules: Optional[str] = None,
    tool_secrets: Optional[Dict[str, str]] = None,
    lang: str = "ko",
) -> List[Dict[str, Any]]:
    """
    JSONL 배치 파일 처리.

    배치 파일 형식 (한 줄에 하나씩):
        {"doc": "/path/to/doc.json", "query": "질문", "img": "/path/to/images/"}
        {"doc": "/path/to/doc2.json", "query": "다른 질문"}
    """
    results = []
    with open(batch_path) as f:
        items = [json.loads(line) for line in f if line.strip()]

    print(f"\n배치 처리: {len(items)}건 | Session: {session_id}")

    for i, item in enumerate(items, 1):
        print(f"\n[{i}/{len(items)}]")
        result = run_query(
            doc_json_path=item["doc"],
            user_query=item["query"],
            reasoner_api_key=reasoner_api_key,
            doc_image_dir=item.get("img"),
            custom_tools_path=custom_tools_path,
            custom_rules=custom_rules,
            tool_secrets=tool_secrets,
            lang=lang,
            session_id=session_id,
        )
        if result:
            results.append(result)

    return results


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="agent API 클라이언트",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # 필수
    parser.add_argument("--api-key", "-k",
        required=True,
        default=os.environ.get("REASONER_API_KEY"),
        help="Reasoner API 키 (필수). OpenAI key for default gpt-5.2, or Novita key. (REASONER_API_KEY 환경변수 가능)")

    # 단일 쿼리
    parser.add_argument("--doc", "-d", help="문서 JSON 경로")
    parser.add_argument("--query", "-q", help="사용자 질문")

    # 배치
    parser.add_argument("--batch", "-b", help="배치 JSONL 파일 경로")

    # 커스텀 도구
    parser.add_argument("--tools", "-t", help="커스텀 Tool .py 파일 경로")
    parser.add_argument("--rules", help="커스텀 규칙 문자열")
    parser.add_argument("--tool-secret", "-s", action="append", metavar="KEY=VALUE",
        help="Tool 시크릿 (반복 가능). 예: -s api_key=sk_xxx")

    # 이미지
    parser.add_argument("--image-dir", "-i", help="문서 이미지 디렉토리")

    # 세션
    parser.add_argument("--session", help="세션 ID (학습데이터 누적용)")
    parser.add_argument("--finalize", action="store_true", help="세션 종료 후 GCS 업로드")

    # 옵션
    parser.add_argument("--lang", "-l", choices=["ko", "en"], default="ko", help="응답 언어")
    parser.add_argument("--steps", "-n", type=int, default=10, help="최대 스텝 수")
    parser.add_argument("--api-url", help=f"API 서버 URL (기본: {API_BASE_URL})")
    parser.add_argument("--reasoner-type", choices=["llm", "vl"], default="llm",
        help="Reasoner 타입: llm(텍스트) 또는 vl(비전)")
    parser.add_argument("--model", help="Reasoner 모델명 (예: gpt-4o)")
    parser.add_argument("--base-url", help="Reasoner 엔드포인트 URL (로컬 vLLM 등)")

    args = parser.parse_args()

    # API URL 설정
    global API_BASE_URL
    if args.api_url:
        API_BASE_URL = args.api_url

    # API 키 확인
    if not args.api_key:
        print("[ERROR] API 키 필요: --api-key 또는 REASONER_API_KEY 환경변수")
        sys.exit(1)

    # tool_secrets 파싱
    tool_secrets = {}
    if args.tool_secret:
        for item in args.tool_secret:
            if "=" in item:
                k, v = item.split("=", 1)
                tool_secrets[k] = v

    # 서버 확인
    if not check_health():
        sys.exit(1)

    # 실행
    if args.batch:
        # 배치 모드
        session_id = args.session or f"batch_{Path(args.batch).stem}"
        run_batch(
            batch_path=args.batch,
            reasoner_api_key=args.api_key,
            session_id=session_id,
            custom_tools_path=args.tools,
            custom_rules=args.rules,
            tool_secrets=tool_secrets or None,
            lang=args.lang,
        )
        if args.finalize:
            finalize_session(session_id)

    elif args.doc and args.query:
        # 단일 쿼리 모드
        run_query(
            doc_json_path=args.doc,
            user_query=args.query,
            reasoner_api_key=args.api_key,
            doc_image_dir=args.image_dir,
            custom_tools_path=args.tools,
            custom_rules=args.rules,
            tool_secrets=tool_secrets or None,
            lang=args.lang,
            session_id=args.session,
            n_steps_max=args.steps,
            reasoner_type=args.reasoner_type,
            reasoner_model_name=args.model,
            reasoner_base_url=args.base_url,
        )
        if args.finalize and args.session:
            finalize_session(args.session)

    else:
        print("[ERROR] --doc + --query 또는 --batch 중 하나를 지정하세요")
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
