#!/usr/bin/env python3
"""
Custom Tool Client Example

Demonstrates how to use the agent API with:
1. Custom tools (.py file path)
2. Custom rules injection
3. Session-based JSONL accumulation
4. GCS upload finalization

Usage:
    python custom_tool_client.py --help

    # Single request with custom tools
    python custom_tool_client.py \
        --doc /path/to/doc.json \
        --query "Analyze the chart on page 4" \
        --tools /path/to/sample_vl_tools.py

    # Batch processing with session accumulation
    python custom_tool_client.py \
        --batch /path/to/queries.jsonl \
        --session my_batch_20240223 \
        --finalize
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

import requests


BASE_URL = "http://10.4.43.13:9024"

# IMPORTANT: Replace with your actual API key (OpenAI for default gpt-5.2 model)
REASONER_API_KEY = "your-openai-api-key-here"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Document Agent V2 Custom Tool Client"
    )

    # Single request mode
    parser.add_argument(
        "--doc",
        type=str,
        help="Path to document JSON file"
    )
    parser.add_argument(
        "--img-dir",
        type=str,
        default=None,
        help="Path to image directory (for docai format)"
    )
    parser.add_argument(
        "--query",
        type=str,
        help="User query to process"
    )

    # Custom tools
    parser.add_argument(
        "--tools",
        type=str,
        default=None,
        help="Path to custom tools .py file"
    )
    parser.add_argument(
        "--rules",
        type=str,
        default=None,
        help="Custom rules to inject (or path to .txt file)"
    )

    # Batch mode
    parser.add_argument(
        "--batch",
        type=str,
        default=None,
        help="Path to JSONL file with batch queries"
    )

    # Session management
    parser.add_argument(
        "--session",
        type=str,
        default=None,
        help="Session ID for accumulating samples"
    )
    parser.add_argument(
        "--finalize",
        action="store_true",
        help="Finalize session and upload to GCS after processing"
    )

    # Options
    parser.add_argument(
        "--lang",
        type=str,
        default="en",
        choices=["ko", "en", "KOREAN", "ENGLISH"],
        help="Output language (default: en)"
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default=BASE_URL,
        help=f"API base URL (default: {BASE_URL})"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose output"
    )

    return parser.parse_args()


def load_custom_rules(rules_arg: Optional[str]) -> Optional[str]:
    """Load custom rules from string or file."""
    if not rules_arg:
        return None

    # Check if it's a file path
    if Path(rules_arg).exists():
        with open(rules_arg, "r", encoding="utf-8") as f:
            return f.read()

    return rules_arg


def run_single_request(
    base_url: str,
    doc_path: str,
    query: str,
    lang: str = "en",
    img_dir: Optional[str] = None,
    tools_path: Optional[str] = None,
    custom_rules: Optional[str] = None,
    session_id: Optional[str] = None,
    verbose: bool = False
) -> dict:
    """Run a single document analysis request."""

    request_body = {
        "doc_json_path": doc_path,
        "user_query": query,
        "lang": lang.upper() if lang in ("ko", "en") else lang,
        "return_train_sample": False,
        "reasoner_api_key": REASONER_API_KEY,
    }

    if img_dir:
        request_body["doc_image_dir"] = img_dir

    if tools_path:
        request_body["custom_tools_path"] = tools_path

    if custom_rules:
        request_body["custom_rules"] = custom_rules

    if session_id:
        request_body["session_id"] = session_id

    if verbose:
        print(f"[Request] POST {base_url}/v2/run")
        print(f"[Request] Body: {json.dumps(request_body, indent=2, ensure_ascii=False)}")

    response = requests.post(
        f"{base_url}/v2/run",
        json=request_body,
        timeout=300
    )

    if response.status_code != 200:
        print(f"[Error] Status {response.status_code}: {response.text}")
        return {"error": response.text, "status_code": response.status_code}

    return response.json()


def run_batch(
    base_url: str,
    batch_path: str,
    lang: str = "en",
    tools_path: Optional[str] = None,
    custom_rules: Optional[str] = None,
    session_id: Optional[str] = None,
    verbose: bool = False
) -> list:
    """Run batch processing from JSONL file.

    JSONL format:
    {"doc": "/path/to/doc.json", "query": "...", "img": "/path/to/images/"}
    {"doc": "/path/to/doc2.json", "query": "..."}
    """
    results = []

    with open(batch_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue

            try:
                item = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"[Error] Line {line_num}: Invalid JSON - {e}")
                continue

            doc_path = item.get("doc")
            query = item.get("query")
            img_dir = item.get("img")

            if not doc_path or not query:
                print(f"[Error] Line {line_num}: Missing 'doc' or 'query'")
                continue

            print(f"\n[Batch {line_num}] Processing: {doc_path}")
            print(f"[Batch {line_num}] Query: {query[:100]}...")

            result = run_single_request(
                base_url=base_url,
                doc_path=doc_path,
                query=query,
                lang=lang,
                img_dir=img_dir,
                tools_path=tools_path,
                custom_rules=custom_rules,
                session_id=session_id,
                verbose=verbose
            )

            results.append({
                "line": line_num,
                "doc": doc_path,
                "query": query,
                "result": result
            })

            if result.get("success"):
                print(f"[Batch {line_num}] Success: {result.get('num_steps', 0)} steps")
                if session_id:
                    print(f"[Batch {line_num}] Session samples: {result.get('session_sample_count', 0)}")
            else:
                print(f"[Batch {line_num}] Failed: {result.get('error', 'Unknown error')}")

    return results


def finalize_session(base_url: str, session_id: str, verbose: bool = False) -> dict:
    """Finalize session and upload to GCS."""

    if verbose:
        print(f"\n[Finalize] POST {base_url}/v2/finalize_session")
        print(f"[Finalize] Session ID: {session_id}")

    response = requests.post(
        f"{base_url}/v2/finalize_session",
        json={"session_id": session_id},
        timeout=300
    )

    if response.status_code != 200:
        print(f"[Error] Status {response.status_code}: {response.text}")
        return {"error": response.text, "status_code": response.status_code}

    return response.json()


def main():
    args = parse_args()

    # Load custom rules
    custom_rules = load_custom_rules(args.rules)

    # Single request mode
    if args.doc and args.query:
        print(f"[Mode] Single request")
        print(f"[Doc] {args.doc}")
        print(f"[Query] {args.query}")

        result = run_single_request(
            base_url=args.base_url,
            doc_path=args.doc,
            query=args.query,
            lang=args.lang,
            img_dir=args.img_dir,
            tools_path=args.tools,
            custom_rules=custom_rules,
            session_id=args.session,
            verbose=args.verbose
        )

        if result.get("success"):
            print(f"\n[Result] Success!")
            print(f"[Steps] {result.get('num_steps', 0)}")
            print(f"[Tokens] {result.get('total_tokens', 0)}")
            print(f"[Duration] {result.get('total_duration_seconds', 0):.2f}s")
            print(f"\n[Answer]\n{result.get('final_answer', '')}")
        else:
            print(f"\n[Error] {result.get('error', 'Unknown error')}")

    # Batch mode
    elif args.batch:
        print(f"[Mode] Batch processing")
        print(f"[Batch] {args.batch}")
        if args.session:
            print(f"[Session] {args.session}")

        results = run_batch(
            base_url=args.base_url,
            batch_path=args.batch,
            lang=args.lang,
            tools_path=args.tools,
            custom_rules=custom_rules,
            session_id=args.session,
            verbose=args.verbose
        )

        # Summary
        success_count = sum(1 for r in results if r.get("result", {}).get("success"))
        print(f"\n[Summary] {success_count}/{len(results)} successful")

    else:
        print("Error: Specify --doc and --query for single request, or --batch for batch processing")
        sys.exit(1)

    # Finalize session if requested
    if args.session and args.finalize:
        print(f"\n[Finalizing session: {args.session}]")

        final_result = finalize_session(
            base_url=args.base_url,
            session_id=args.session,
            verbose=args.verbose
        )

        if final_result.get("success"):
            print(f"[Success] Session finalized!")
            print(f"[Samples] {final_result.get('sample_count', 0)}")
            print(f"[GCS Path] {final_result.get('gcs_path', '')}")
        else:
            print(f"[Error] {final_result.get('error', 'Unknown error')}")


if __name__ == "__main__":
    main()
