#!/usr/bin/env python3
"""
agent API Real Client Example

This script demonstrates the full workflow of using the agent API
with custom VL tools to analyze document images.
Supports passing secrets to custom tools via --tool-secret option.

Prerequisites:
    1. Start the API server (see run_server.sh)

Usage:
    python real_client_example.py
    python real_client_example.py -s api_key=sk_xxx
    python real_client_example.py -i -s api_key=sk_xxx
"""
import os
import sys
import json
import requests
from pathlib import Path
from typing import Optional, Dict, Any

# =============================================================================
# Configuration
# =============================================================================

API_BASE_URL = os.environ.get("DOC_AGENT_API_URL", "http://10.4.43.13:9024")
SESSION_ID = "real_example_session_001"

# IMPORTANT: Replace with your actual API key (OpenAI for default gpt-5.2 model)
REASONER_API_KEY = "your-openai-api-key-here"

# Path to VL tools file (relative to this script)
SCRIPT_DIR = Path(__file__).parent
TOOLS_PATH = str(SCRIPT_DIR / "real_vl_tools.py")

# =============================================================================
# Document Configurations
# =============================================================================

DOCUMENTS = {
    "financial_report": {
        "doc_json": "/ex_disk2/mhpark/poc/docai/out/32_IM증권/00163f84.json",
        "image_dir": "/ex_disk2/mhpark/poc/docai/out/img/32_IM증권/00163f84/",
        "description": "HYBE Stock Analysis Report (NewJeans Hot100 Chart Entry)",
        "queries": [
            {
                "query": "이 리포트의 목표주가와 현재주가를 알려주고, 2페이지의 목표주가 산출 테이블을 분석해주세요.",
                "expected_tools": ["search", "analyze_visual"],
                "focus": "table"
            },
            {
                "query": "4페이지에 있는 미국 Vinyl/CD 판매량 표를 분석하고, K-POP 아티스트들의 순위를 정리해주세요.",
                "expected_tools": ["GetPage", "analyze_visual", "extract_table"],
                "focus": "table"
            },
            {
                "query": "하이브의 2024년 예상 매출과 영업이익을 알려주세요. 관련 차트가 있다면 분석해주세요.",
                "expected_tools": ["search", "ReadFullDocument", "analyze_visual"],
                "focus": "chart"
            }
        ]
    },
    "research_report": {
        "doc_json": "/ex_disk2/mhpark/poc/docai/out/31_KISTEP/119fbbe1.json",
        "image_dir": "/ex_disk2/mhpark/poc/docai/out/img/31_KISTEP/119fbbe1/",
        "description": "Innovation Challenge Project Support Report (KISTEP)",
        "queries": [
            {
                "query": "100페이지의 사업 주요 성과 테이블을 분석해주세요. 플라즈마 기술 관련 성과를 중심으로 설명해주세요.",
                "expected_tools": ["GetPage", "analyze_visual"],
                "focus": "table"
            },
            {
                "query": "104페이지의 시스템 다이어그램을 분석해주세요. 폐플라스틱 처리 공정이 어떻게 구성되어 있나요?",
                "expected_tools": ["GetPage", "analyze_visual"],
                "focus": "diagram"
            }
        ]
    }
}

# Custom rules to encourage VL tool usage
CUSTOM_RULES = """- When the user asks to analyze a table or chart, you MUST use analyze_visual or extract_table tool
- Before analyzing visual elements, use GetPage to check the page content first
- When extracting numerical data from tables, use extract_table for accurate values
- For diagrams or flowcharts, set analysis_focus to 'diagram' in analyze_visual
- Always cite the page number when reporting visual analysis results"""


# =============================================================================
# Helper Functions
# =============================================================================

def check_api_health() -> bool:
    """Check if the API server is running and healthy."""
    try:
        response = requests.get(f"{API_BASE_URL}/health", timeout=5)
        if response.status_code == 200:
            health = response.json()
            print(f"[OK] API Server: {health['status']}")
            print(f"     Version: {health['version']}")
            print(f"     Sandbox Mode: {health.get('sandbox_mode', False)}")
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


def check_prerequisites(tool_secrets: dict = None) -> bool:
    """Check if all prerequisites are met."""
    all_ok = True

    # Check tools file
    if os.path.exists(TOOLS_PATH):
        print(f"[OK] Tools file: {TOOLS_PATH}")
    else:
        print(f"[ERROR] Tools file not found: {TOOLS_PATH}")
        all_ok = False

    # Check for api_key (from tool_secrets or env)
    api_key = (tool_secrets or {}).get("api_key") or os.environ.get("NOVITA_API_KEY")
    if api_key:
        source = "(from -s)" if (tool_secrets or {}).get("api_key") else "(from env)"
        print(f"[OK] API Key: {source}")
    else:
        print(f"[WARN] API Key not set - VL tools may fail")
        print(f"       Use: -s api_key=YOUR_KEY or export NOVITA_API_KEY=YOUR_KEY")

    # Check document paths
    for name, config in DOCUMENTS.items():
        if os.path.exists(config["doc_json"]):
            print(f"[OK] Document [{name}]: {config['description']}")
        else:
            print(f"[WARN] Document [{name}] not found: {config['doc_json']}")

    return all_ok


def parse_tool_secrets(secret_args: list) -> dict:
    """
    Parse --tool-secret arguments into a dict.

    Args:
        secret_args: List of "key=value" strings

    Returns:
        Dict of secrets
    """
    secrets = {}
    if secret_args:
        for item in secret_args:
            if "=" in item:
                key, value = item.split("=", 1)
                secrets[key] = value
            else:
                print(f"[WARN] Invalid secret format (expected key=value): {item}")
    return secrets


def run_single_query(
    doc_config: Dict[str, Any],
    query_config: Dict[str, Any],
    use_session: bool = True,
    lang: str = "ko",
    tool_secrets: dict = None
) -> Optional[Dict[str, Any]]:
    """
    Run a single query against the API.

    Args:
        doc_config: Document configuration with paths
        query_config: Query configuration with query text and expected tools
        use_session: Whether to use session-based accumulation
        lang: Response language ("ko" or "en")
        tool_secrets: Secrets dict for custom tools (e.g., {"api_key": "sk_xxx"})

    Returns:
        API response dict or None on failure
    """
    print(f"\n{'='*70}")
    print(f"Query: {query_config['query'][:70]}...")
    print(f"Expected Tools: {query_config.get('expected_tools', [])}")
    print(f"{'='*70}")

    request_body = {
        "doc_json_path": doc_config["doc_json"],
        "doc_image_dir": doc_config["image_dir"],
        "user_query": query_config["query"],
        "lang": lang,  # "ko" or "en"
        "custom_tools_path": TOOLS_PATH,
        "custom_rules": CUSTOM_RULES,
        "return_trace": True,
        "n_steps_max": 10,
        "reasoner_api_key": REASONER_API_KEY,  # Required: Your API key
    }

    if use_session:
        request_body["session_id"] = SESSION_ID

    # Pass tool secrets if provided
    if tool_secrets:
        request_body["tool_secrets"] = tool_secrets

    try:
        print("\nSending request...")
        response = requests.post(
            f"{API_BASE_URL}/v2/run",
            json=request_body,
            timeout=300  # 5 minute timeout
        )

        if response.status_code != 200:
            print(f"[ERROR] Status {response.status_code}")
            print(f"        Detail: {response.text[:500]}")
            return None

        result = response.json()

        # Print summary
        print(f"\n[Result Summary]")
        print(f"  Success: {result['success']}")
        print(f"  Steps: {result['num_steps']}")
        print(f"  Tokens: {result['total_tokens']}")
        print(f"  Duration: {result['total_duration_seconds']:.2f}s")

        if use_session:
            print(f"  Session Samples: {result.get('session_sample_count', 'N/A')}")

        # Print tools used
        print(f"\n[Tools Used]")
        tools_used = []
        for step in result.get("steps_reasoning", []):
            if step.get("action"):
                tool_name = step["action"]["name"]
                tools_used.append(tool_name)
                print(f"  Step {step['step_number']}: {tool_name}")

        # Check if expected tools were used
        expected = set(query_config.get("expected_tools", []))
        actual = set(tools_used)
        if expected:
            used_expected = expected & actual
            missing = expected - actual
            if missing:
                print(f"\n[Note] Expected tools not used: {missing}")

        # Print answer preview
        print(f"\n[Answer Preview]")
        answer = result.get("final_answer", "")
        preview_len = 600
        if len(answer) > preview_len:
            print(answer[:preview_len] + "...")
        else:
            print(answer)

        return result

    except requests.exceptions.Timeout:
        print("[ERROR] Request timed out (>5 min)")
        return None
    except Exception as e:
        print(f"[ERROR] {e}")
        return None


def finalize_session() -> Optional[Dict[str, Any]]:
    """Finalize the session and upload to GCS."""
    print(f"\n{'='*70}")
    print("Finalizing Session...")
    print(f"{'='*70}")

    try:
        response = requests.post(
            f"{API_BASE_URL}/v2/finalize_session",
            json={"session_id": SESSION_ID},
            timeout=60
        )

        if response.status_code == 200:
            result = response.json()
            print(f"\n[Session Finalized]")
            print(f"  Session ID: {result['session_id']}")
            print(f"  Sample Count: {result['sample_count']}")
            print(f"  GCS Path: {result.get('gcs_path', 'N/A')}")
            print(f"  Success: {result['success']}")
            if result.get('error'):
                print(f"  Error: {result['error']}")
            return result
        else:
            print(f"[ERROR] Finalization failed: {response.text}")
            return None

    except Exception as e:
        print(f"[ERROR] {e}")
        return None


def run_demo(doc_name: str = "financial_report", query_count: int = 2, tool_secrets: dict = None):
    """Run a demo with specified document."""
    if doc_name not in DOCUMENTS:
        print(f"[ERROR] Unknown document: {doc_name}")
        print(f"        Available: {list(DOCUMENTS.keys())}")
        return

    doc = DOCUMENTS[doc_name]
    print(f"\n{'='*70}")
    print(f"Running Demo: {doc['description']}")
    print(f"{'='*70}")

    queries = doc["queries"][:query_count]

    for i, query in enumerate(queries, 1):
        print(f"\n[Query {i}/{len(queries)}]")
        run_single_query(doc, query, use_session=True, lang="ko", tool_secrets=tool_secrets)


# =============================================================================
# Main
# =============================================================================

def main(doc_name: str = "financial_report", query_count: int = 2, tool_secrets: dict = None):
    """Main entry point."""
    print("="*70)
    print("agent Real Client Example")
    print("="*70)

    # 1. Check API health
    print("\n[1] Checking API Server...")
    if not check_api_health():
        sys.exit(1)

    # 2. Check prerequisites
    print("\n[2] Checking Prerequisites...")
    check_prerequisites(tool_secrets)

    # 3. Run demo queries
    print("\n[3] Running Demo Queries...")
    run_demo(doc_name, query_count=query_count, tool_secrets=tool_secrets)

    # 4. Ask about session finalization
    print("\n" + "="*70)
    try:
        user_input = input("Finalize session and upload to GCS? (y/n): ").strip().lower()
        if user_input == 'y':
            finalize_session()
        else:
            print("Session kept active for further processing.")
            print(f"Session ID: {SESSION_ID}")
    except KeyboardInterrupt:
        print("\nSkipped.")

    print("\n" + "="*70)
    print("Demo completed!")
    print("="*70)


def interactive_mode(tool_secrets: dict = None):
    """Interactive mode for custom queries."""
    print("="*70)
    print("Interactive Mode")
    print("="*70)

    # Check prerequisites
    if not check_api_health():
        return

    check_prerequisites(tool_secrets)

    print("\nAvailable documents:")
    for name, config in DOCUMENTS.items():
        print(f"  - {name}: {config['description']}")

    while True:
        print("\n" + "-"*50)
        doc_name = input("Document name (or 'quit'): ").strip()

        if doc_name.lower() == 'quit':
            break

        if doc_name not in DOCUMENTS:
            print(f"Unknown document. Available: {list(DOCUMENTS.keys())}")
            continue

        query = input("Your query: ").strip()
        if not query:
            continue

        lang = input("Language (ko/en, default: ko): ").strip() or "ko"
        if lang not in ("ko", "en"):
            lang = "ko"

        doc = DOCUMENTS[doc_name]
        query_config = {
            "query": query,
            "expected_tools": [],
            "focus": "general"
        }

        run_single_query(doc, query_config, use_session=False, lang=lang, tool_secrets=tool_secrets)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="agent Real Client Example")
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Run in interactive mode"
    )
    parser.add_argument(
        "--document", "-d",
        default="financial_report",
        choices=list(DOCUMENTS.keys()),
        help="Document to use for demo"
    )
    parser.add_argument(
        "--queries", "-q",
        type=int,
        default=2,
        help="Number of queries to run in demo"
    )
    parser.add_argument(
        "--tool-secret", "-s",
        action="append",
        metavar="KEY=VALUE",
        help="Tool secrets (key=value format, can repeat). e.g., -s api_key=sk_xxx -s db_url=..."
    )

    args = parser.parse_args()

    # Parse tool secrets
    tool_secrets = parse_tool_secrets(args.tool_secret)

    if args.interactive:
        interactive_mode(tool_secrets=tool_secrets if tool_secrets else None)
    else:
        main(
            doc_name=args.document,
            query_count=args.queries,
            tool_secrets=tool_secrets if tool_secrets else None
        )
