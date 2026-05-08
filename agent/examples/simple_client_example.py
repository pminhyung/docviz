#!/usr/bin/env python3
"""
agent API Simple Client Example

Single document, single query test script.
Supports passing secrets to custom tools via --tool-secret option.

Usage:
    python simple_client_example.py
    python simple_client_example.py -s api_key=sk_xxx
    python simple_client_example.py --query "분석해주세요" -s api_key=sk_xxx

Prerequisites:
    1. Start the API server (see run_server.sh)
"""
import os
import sys
import json
import argparse
import requests
from pathlib import Path

# =============================================================================
# Configuration
# =============================================================================

API_BASE_URL = os.environ.get("DOC_AGENT_API_URL", "http://10.4.43.13:9024")

# IMPORTANT: Replace with your actual API key (OpenAI for default gpt-5.2 model)
REASONER_API_KEY = "your-openai-api-key-here"

# Path to VL tools file
SCRIPT_DIR = Path(__file__).parent
TOOLS_PATH = str(SCRIPT_DIR / "real_vl_tools.py")

# Default test document
DEFAULT_DOC = {
    "doc_json": "/ex_disk2/mhpark/poc/docai/out/32_IM증권/00163f84.json",
    "image_dir": "/ex_disk2/mhpark/poc/docai/out/img/32_IM증권/00163f84/",
    "description": "HYBE Stock Analysis Report"
}

DEFAULT_QUERY = "이 리포트의 목표주가와 현재주가를 알려주고, 투자의견을 요약해주세요."

# Custom rules for VL tool usage
CUSTOM_RULES = """- When the user asks to analyze a table or chart, use analyze_visual or extract_table tool
- Before analyzing visual elements, use GetPage to check the page content first
- Always cite the page number when reporting visual analysis results"""


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


def run_single_query(
    doc_json_path: str,
    doc_image_dir: str,
    user_query: str,
    lang: str = "ko",
    tool_secrets: dict = None,
    use_custom_tools: bool = True,
    verbose: bool = True,
    reasoner_api_key: str = REASONER_API_KEY,
) -> dict:
    """
    Run a single query against the API.

    Args:
        doc_json_path: Path to document JSON file
        doc_image_dir: Path to image directory
        user_query: User query string
        lang: Response language ("ko" or "en")
        tool_secrets: Secrets dict for custom tools (e.g., {"api_key": "sk_xxx"})
        use_custom_tools: Whether to use custom tools
        verbose: Print detailed output
        reasoner_api_key: API key for reasoning model (required)

    Returns:
        API response dict
    """
    if verbose:
        print(f"\n{'='*60}")
        print(f"Document: {doc_json_path}")
        print(f"Query: {user_query[:60]}...")
        print(f"Language: {lang}")
        print(f"Custom Tools: {'Enabled' if use_custom_tools else 'Disabled'}")
        print(f"{'='*60}")

    # Build request body
    request_body = {
        "doc_json_path": doc_json_path,
        "doc_image_dir": doc_image_dir,
        "user_query": user_query,
        "lang": lang,
        "return_trace": True,
        "n_steps_max": 10,
        "reasoner_api_key": reasoner_api_key,
    }

    # Add custom tools if enabled
    if use_custom_tools:
        request_body["custom_tools_path"] = TOOLS_PATH
        request_body["custom_rules"] = CUSTOM_RULES

        # Pass tool secrets if provided
        if tool_secrets:
            request_body["tool_secrets"] = tool_secrets

    try:
        if verbose:
            print("\nSending request...")

        response = requests.post(
            f"{API_BASE_URL}/v2/run",
            json=request_body,
            timeout=300  # 5 minute timeout
        )

        if response.status_code != 200:
            print(f"[ERROR] Status {response.status_code}")
            print(f"        Detail: {response.text[:500]}")
            return {"success": False, "error": response.text}

        result = response.json()

        if verbose:
            # Print summary
            print(f"\n[Result Summary]")
            print(f"  Success: {result['success']}")
            print(f"  Steps: {result['num_steps']}")
            print(f"  Tokens: {result['total_tokens']}")
            print(f"  Duration: {result['total_duration_seconds']:.2f}s")

            # Print tools used
            print(f"\n[Tools Used]")
            for step in result.get("steps_reasoning", []):
                if step.get("action"):
                    tool_name = step["action"]["name"]
                    print(f"  Step {step['step_number']}: {tool_name}")

            # Print answer
            print(f"\n[Final Answer]")
            print("-" * 60)
            answer = result.get("final_answer", "")
            print(answer)
            print("-" * 60)

        return result

    except requests.exceptions.Timeout:
        print("[ERROR] Request timed out (>5 min)")
        return {"success": False, "error": "timeout"}
    except Exception as e:
        print(f"[ERROR] {e}")
        return {"success": False, "error": str(e)}


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


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="agent Simple Client - Single document, single query test"
    )
    parser.add_argument(
        "--doc-json", "-d",
        default=DEFAULT_DOC["doc_json"],
        help="Path to document JSON file"
    )
    parser.add_argument(
        "--image-dir", "-i",
        default=DEFAULT_DOC["image_dir"],
        help="Path to image directory"
    )
    parser.add_argument(
        "--query", "-q",
        default=DEFAULT_QUERY,
        help="User query"
    )
    parser.add_argument(
        "--lang", "-l",
        choices=["ko", "en"],
        default="ko",
        help="Response language"
    )
    parser.add_argument(
        "--tool-secret", "-s",
        action="append",
        metavar="KEY=VALUE",
        help="Tool secrets (key=value format, can repeat). e.g., -s api_key=sk_xxx -s db_url=..."
    )
    parser.add_argument(
        "--no-custom-tools",
        action="store_true",
        help="Disable custom tools (text-only analysis)"
    )
    parser.add_argument(
        "--api-url",
        default=None,
        help="API server URL (default: http://10.4.43.13:9024)"
    )

    args = parser.parse_args()

    # Override API URL if provided
    global API_BASE_URL
    if args.api_url:
        API_BASE_URL = args.api_url

    print("=" * 60)
    print("agent Simple Client")
    print("=" * 60)

    # 1. Check API health
    print("\n[1] Checking API Server...")
    if not check_api_health():
        sys.exit(1)

    # 2. Check prerequisites
    print("\n[2] Checking Prerequisites...")

    if os.path.exists(args.doc_json):
        print(f"[OK] Document: {args.doc_json}")
    else:
        print(f"[ERROR] Document not found: {args.doc_json}")
        sys.exit(1)

    # Parse tool secrets
    tool_secrets = parse_tool_secrets(args.tool_secret)

    if not args.no_custom_tools:
        if os.path.exists(TOOLS_PATH):
            print(f"[OK] Custom Tools: {TOOLS_PATH}")
        else:
            print(f"[WARN] Custom Tools not found: {TOOLS_PATH}")

        # Check for api_key (from args or env)
        api_key = tool_secrets.get("api_key") or os.environ.get("NOVITA_API_KEY")
        if api_key:
            source = "(from -s)" if tool_secrets.get("api_key") else "(from env)"
            print(f"[OK] API Key: {source}")
        else:
            print("[WARN] API Key not set - custom tools requiring API may fail")

    # 3. Run query
    print("\n[3] Running Query...")
    result = run_single_query(
        doc_json_path=args.doc_json,
        doc_image_dir=args.image_dir,
        user_query=args.query,
        lang=args.lang,
        tool_secrets=tool_secrets if tool_secrets else None,
        use_custom_tools=not args.no_custom_tools,
        verbose=True
    )

    # 4. Summary
    print("\n" + "=" * 60)
    if result.get("success"):
        print("Test completed successfully!")
    else:
        print(f"Test failed: {result.get('error', 'Unknown error')}")
    print("=" * 60)

    return 0 if result.get("success") else 1


if __name__ == "__main__":
    sys.exit(main())
