#!/usr/bin/env python3
"""
agent VL Client — Vision-Language 도구를 활용한 문서 분석 클라이언트

문서 JSON 경로 + 이미지 디렉토리를 전달하여 VL 추론 포함 reasoning을 실행한다.
커스텀 VL 도구(vl_tools.py)를 자동으로 로드하며, context["call_vl"]을 통해
파이프라인의 VL 모델을 호출하고 SFT 학습 데이터를 동시에 생성한다.

Usage:
    # 기본 실행 (단일 쿼리)
    python vl_client.py \\
        --doc-json /path/to/doc.json \\
        --image-dir /path/to/images/ \\
        --query "2페이지의 차트를 분석해주세요"

    # 세션 누적 + 종료 시 GCS 업로드
    python vl_client.py \\
        --doc-json /path/to/doc.json \\
        --image-dir /path/to/images/ \\
        --query "테이블 분석" \\
        --session-id my_session_001 \\
        --finalize

    # 영어 응답
    python vl_client.py \\
        --doc-json /path/to/doc.json \\
        --image-dir /path/to/images/ \\
        --query "Analyze the chart on page 3" \\
        --lang en

Prerequisites:
    1. Start the API server (see run_server.sh)
    2. Reasoner API key (--reasoner-api-key or REASONER_API_KEY env)
"""
import os
import sys
import json
import argparse
import requests
from pathlib import Path
from typing import Optional, Dict, Any


# =============================================================================
# Configuration
# =============================================================================

API_BASE_URL = os.environ.get("DOC_AGENT_API_URL", "http://10.4.43.13:9024")

# Path to VL tools file (relative to this script)
SCRIPT_DIR = Path(__file__).parent
VL_TOOLS_PATH = str(SCRIPT_DIR / "vl_tools.py")

# Custom rules for VL tool usage
CUSTOM_RULES = """- 사용자가 표나 차트 분석을 요청하면 analyze_page_image 또는 extract_table 도구를 사용하세요
- 시각적 요소 분석 전에 먼저 search나 GetPage로 해당 페이지 내용을 확인하세요
- 분석 결과 보고 시 항상 페이지 번호를 인용하세요
- 여러 페이지의 시각적 요소를 비교할 때는 compare_page_images 도구를 사용하세요"""

# Default test document
DEFAULT_DOC = {
    "doc_json": "/ex_disk2/mhpark/poc/docai/out/32_IM증권/00163f84.json",
    "image_dir": "/ex_disk2/mhpark/poc/docai/out/img/32_IM증권/00163f84/",
}

DEFAULT_QUERY = "이 리포트의 목표주가와 현재주가를 알려주고, 관련 차트나 테이블이 있다면 분석해주세요."


# =============================================================================
# Functions
# =============================================================================

def check_api_health() -> bool:
    """Check if the API server is running."""
    try:
        response = requests.get(f"{API_BASE_URL}/health", timeout=5)
        if response.status_code == 200:
            health = response.json()
            print(f"[OK] API Server: {health['status']}")
            print(f"     Version: {health['version']}")
            return True
        else:
            print(f"[ERROR] API returned status {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print(f"[ERROR] Cannot connect to API server: {API_BASE_URL}")
        print("        Start the server with: ./run_server.sh")
        return False
    except Exception as e:
        print(f"[ERROR] Health check failed: {e}")
        return False


def check_prerequisites(doc_json: str, image_dir: str) -> bool:
    """Check if all prerequisites are met."""
    all_ok = True

    # Check VL tools file
    if os.path.exists(VL_TOOLS_PATH):
        print(f"[OK] VL Tools: {VL_TOOLS_PATH}")
    else:
        print(f"[ERROR] VL Tools not found: {VL_TOOLS_PATH}")
        all_ok = False

    # Check document JSON
    if os.path.exists(doc_json):
        print(f"[OK] Document JSON: {doc_json}")
    else:
        print(f"[ERROR] Document not found: {doc_json}")
        all_ok = False

    # Check image directory
    if os.path.isdir(image_dir):
        # Count image files
        images = [f for f in os.listdir(image_dir) if f.endswith(".png")]
        print(f"[OK] Image Directory: {image_dir} ({len(images)} images)")
    else:
        print(f"[WARN] Image directory not found: {image_dir}")
        print("       VL tools will not be able to analyze page images.")

    return all_ok


def run_query(
    doc_json_path: str,
    doc_image_dir: str,
    user_query: str,
    lang: str = "ko",
    session_id: Optional[str] = None,
    reasoner_api_key: str = "",
    custom_rules: str = CUSTOM_RULES,
    n_steps_max: int = 10,
    verbose: bool = True,
) -> Optional[Dict[str, Any]]:
    """
    Run a single VL query against the API.

    Args:
        doc_json_path: Path to document JSON file
        doc_image_dir: Path to image directory
        user_query: User query string
        lang: Response language ("ko" or "en")
        session_id: Session ID for accumulation (optional)
        reasoner_api_key: API key for reasoning model
        custom_rules: Custom rules for VL tool usage
        n_steps_max: Maximum reasoning steps
        verbose: Print detailed output

    Returns:
        API response dict or None on failure
    """
    if verbose:
        print(f"\n{'='*60}")
        print(f"Document: {doc_json_path}")
        print(f"Images:   {doc_image_dir}")
        print(f"Query:    {user_query[:70]}...")
        print(f"Language: {lang}")
        if session_id:
            print(f"Session:  {session_id}")
        print(f"{'='*60}")

    request_body = {
        "doc_json_path": doc_json_path,
        "doc_image_dir": doc_image_dir,
        "user_query": user_query,
        "lang": lang,
        "custom_tools_path": VL_TOOLS_PATH,
        "custom_rules": custom_rules,
        "return_trace": True,
        "n_steps_max": n_steps_max,
        "reasoner_api_key": reasoner_api_key,
    }

    if session_id:
        request_body["session_id"] = session_id

    try:
        if verbose:
            print("\nSending request...")

        response = requests.post(
            f"{API_BASE_URL}/v2/run",
            json=request_body,
            timeout=300,
        )

        if response.status_code != 200:
            print(f"[ERROR] Status {response.status_code}")
            print(f"        Detail: {response.text[:500]}")
            return None

        result = response.json()

        if verbose:
            print(f"\n[Result Summary]")
            print(f"  Success:  {result['success']}")
            print(f"  Steps:    {result['num_steps']}")
            print(f"  Tokens:   {result['total_tokens']}")
            print(f"  Duration: {result['total_duration_seconds']:.2f}s")

            if session_id:
                print(f"  Session Samples: {result.get('session_sample_count', 'N/A')}")

            # Print tools used
            print(f"\n[Tools Used]")
            vl_tools_used = []
            for step in result.get("steps_reasoning", []):
                if step.get("action"):
                    tool_name = step["action"]["name"]
                    marker = " (VL)" if tool_name in ("analyze_page_image", "extract_table", "compare_page_images") else ""
                    print(f"  Step {step['step_number']}: {tool_name}{marker}")
                    if marker:
                        vl_tools_used.append(tool_name)

            if not vl_tools_used:
                print("  [Note] No VL tools were used in this query.")

            # Print answer
            print(f"\n[Final Answer]")
            print("-" * 60)
            answer = result.get("final_answer", "")
            print(answer)
            print("-" * 60)

        return result

    except requests.exceptions.Timeout:
        print("[ERROR] Request timed out (>5 min)")
        return None
    except Exception as e:
        print(f"[ERROR] {e}")
        return None


def finalize_session(session_id: str) -> Optional[Dict[str, Any]]:
    """Finalize the session and upload to GCS."""
    print(f"\n{'='*60}")
    print(f"Finalizing Session: {session_id}")
    print(f"{'='*60}")

    try:
        response = requests.post(
            f"{API_BASE_URL}/v2/finalize_session",
            json={"session_id": session_id},
            timeout=60,
        )

        if response.status_code == 200:
            result = response.json()
            print(f"\n[Session Finalized]")
            print(f"  Session ID:   {result['session_id']}")
            print(f"  Sample Count: {result['sample_count']}")
            print(f"  GCS Path:     {result.get('gcs_path', 'N/A')}")
            print(f"  Success:      {result['success']}")
            if result.get("error"):
                print(f"  Error:        {result['error']}")
            return result
        else:
            print(f"[ERROR] Finalization failed: {response.text}")
            return None

    except Exception as e:
        print(f"[ERROR] {e}")
        return None


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="agent VL Client — Vision-Language 도구를 활용한 문서 분석",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --doc-json /path/to/doc.json --image-dir /path/to/images/ --query "차트 분석"
  %(prog)s -d /path/to/doc.json -i /path/to/images/ -q "테이블 추출" --session-id s001 --finalize
        """,
    )
    parser.add_argument(
        "--doc-json", "-d",
        default=DEFAULT_DOC["doc_json"],
        help="Path to document JSON file",
    )
    parser.add_argument(
        "--image-dir", "-i",
        default=DEFAULT_DOC["image_dir"],
        help="Path to document image directory",
    )
    parser.add_argument(
        "--query", "-q",
        default=DEFAULT_QUERY,
        help="User query",
    )
    parser.add_argument(
        "--lang", "-l",
        choices=["ko", "en"],
        default="ko",
        help="Response language (default: ko)",
    )
    parser.add_argument(
        "--session-id",
        default=None,
        help="Session ID for train sample accumulation",
    )
    parser.add_argument(
        "--finalize",
        action="store_true",
        help="Finalize session after query (upload to GCS)",
    )
    parser.add_argument(
        "--reasoner-api-key",
        default=os.environ.get("REASONER_API_KEY", ""),
        help="API key for reasoning model (or set REASONER_API_KEY env)",
    )
    parser.add_argument(
        "--api-url",
        default=None,
        help=f"API server URL (default: {API_BASE_URL})",
    )
    parser.add_argument(
        "--steps", "-n",
        type=int,
        default=10,
        help="Maximum reasoning steps (default: 10)",
    )

    args = parser.parse_args()

    # Override API URL if provided
    global API_BASE_URL
    if args.api_url:
        API_BASE_URL = args.api_url

    print("=" * 60)
    print("agent VL Client")
    print("=" * 60)

    # 1. Check API health
    print("\n[1] Checking API Server...")
    if not check_api_health():
        sys.exit(1)

    # 2. Check prerequisites
    print("\n[2] Checking Prerequisites...")
    check_prerequisites(args.doc_json, args.image_dir)

    # 3. Run query
    print("\n[3] Running VL Query...")
    result = run_query(
        doc_json_path=args.doc_json,
        doc_image_dir=args.image_dir,
        user_query=args.query,
        lang=args.lang,
        session_id=args.session_id,
        reasoner_api_key=args.reasoner_api_key,
        n_steps_max=args.steps,
    )

    # 4. Finalize session if requested
    if args.finalize and args.session_id and result and result.get("success"):
        print("\n[4] Finalizing Session...")
        finalize_session(args.session_id)

    # 5. Summary
    print("\n" + "=" * 60)
    if result and result.get("success"):
        print("VL analysis completed successfully!")
    else:
        print(f"VL analysis failed: {result.get('error', 'Unknown error') if result else 'No response'}")
    print("=" * 60)

    return 0 if (result and result.get("success")) else 1


if __name__ == "__main__":
    sys.exit(main())
