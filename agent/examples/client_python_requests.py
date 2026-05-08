#!/usr/bin/env python3
"""
Python Client Example for Document Agent V2 API

This script demonstrates how to use the Document Agent V2 API
with the Python requests library.

Usage:
    python client_python_requests.py \
        --doc_path /path/to/document.json \
        --query "Your question here" \
        --trace \
        --validate

Requirements:
    pip install requests

Environment:
    Ensure the API server is running (see run_server.sh, default port 9024)
"""

import argparse
import json
import sys
from typing import Optional

try:
    import requests
except ImportError:
    print("Error: requests library not installed")
    print("Install with: pip install requests")
    sys.exit(1)

# IMPORTANT: Replace with your actual API key (OpenAI for default gpt-5.2 model)
REASONER_API_KEY = "your-openai-api-key-here"


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Python client for Document Agent V2 API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--base_url",
        type=str,
        default="http://10.4.43.13:9024",
        help="API base URL (default: http://10.4.43.13:9024)",
    )

    parser.add_argument(
        "--doc_path",
        type=str,
        required=True,
        help="Path to document JSON file",
    )

    parser.add_argument(
        "--doc_path_2",
        type=str,
        default=None,
        help="Optional second document path",
    )

    parser.add_argument(
        "--query",
        type=str,
        required=True,
        help="User query to answer",
    )

    parser.add_argument(
        "--lang",
        type=str,
        choices=["ENGLISH", "KOREAN"],
        default="ENGLISH",
        help="Output language (default: ENGLISH)",
    )

    parser.add_argument(
        "--trace",
        action="store_true",
        help="Request full trace in response",
    )

    parser.add_argument(
        "--train_sample",
        action="store_true",
        help="Request train_sample in response",
    )

    parser.add_argument(
        "--validate",
        action="store_true",
        help="Also validate the trace after running",
    )

    parser.add_argument(
        "--max_steps",
        type=int,
        default=20,
        help="Maximum agent steps (default: 20)",
    )

    return parser.parse_args()


def health_check(base_url: str) -> dict:
    """
    Check API health status.

    Args:
        base_url: API base URL

    Returns:
        Health response dict with:
        - status: "healthy" if server is up
        - version: API version string
        - models_available: Whether model API keys are configured
    """
    url = f"{base_url}/health"
    response = requests.get(url, timeout=5)
    response.raise_for_status()
    return response.json()


def run_agent(
    base_url: str,
    doc_json_path: str,
    user_query: str,
    lang: str = "ENGLISH",
    doc_json_path_2: Optional[str] = None,
    return_trace: bool = False,
    return_train_sample: bool = False,
    n_steps_max: int = 20,
    reasoner_api_key: str = REASONER_API_KEY,
) -> dict:
    """
    Run the document agent.

    Args:
        base_url: API base URL
        doc_json_path: Path to document JSON file
        user_query: Question to answer
        lang: Output language (ENGLISH or KOREAN)
        doc_json_path_2: Optional second document path
        return_trace: Include full trace in response
        return_train_sample: Include train_sample in response
        n_steps_max: Maximum agent steps
        reasoner_api_key: API key for reasoning model (required)

    Returns:
        Response dict with:
        - final_answer: The agent's answer
        - steps_reasoning: List of reasoning steps
            - step_number: Sequential step number
            - step_type: Type of step (reasoning, tool_call, etc.)
            - step_name: Description of what the step does
            - action: Tool action taken (name and arguments)
            - duration: Step duration in seconds
        - inputs_used: Count of document inputs used
        - warnings: Validation warnings from output validator
        - session_id: Unique session identifier
        - total_tokens: Total tokens used in session
        - success: Whether agent completed successfully
        - trace: Full trace (if return_trace=True)
        - train_sample: Training sample (if return_train_sample=True)
    """
    url = f"{base_url}/v2/run"

    # Build request payload
    # Required fields:
    # - doc_json_path: Path to document JSON file
    # - user_query: The question to answer
    # - reasoner_api_key: API key for reasoning model
    payload = {
        "doc_json_path": doc_json_path,
        "user_query": user_query,
        "lang": lang,
        "single_doc": True,
        "n_steps_max": n_steps_max,
        "return_trace": return_trace,
        "return_train_sample": return_train_sample,
        "reasoner_api_key": reasoner_api_key,
    }

    # Add optional second document
    if doc_json_path_2:
        payload["doc_json_path_2"] = doc_json_path_2
        payload["single_doc"] = False

    # Make request
    response = requests.post(
        url,
        json=payload,
        timeout=300,  # 5 minute timeout for long queries
    )
    response.raise_for_status()
    return response.json()


def validate_trace(
    base_url: str,
    trace: dict,
    language: str = "ENGLISH",
    has_documents: bool = True,
) -> dict:
    """
    Validate a trace using the validation endpoint.

    Args:
        base_url: API base URL
        trace: Trace dict to validate
        language: Expected language
        has_documents: Whether documents were provided

    Returns:
        Validation response with:
        - ok: True if no errors
        - errors: List of validation errors
        - warnings: List of validation warnings
        - stats: Statistics
            - steps_count: Total steps
            - tool_invoke_count: Number of tool invocations
            - citation_count: Number of [N] citations
    """
    url = f"{base_url}/v2/validate"

    payload = {
        "trace": trace,
        "language": language,
        "has_documents": has_documents,
    }

    response = requests.post(url, json=payload, timeout=30)
    response.raise_for_status()
    return response.json()


def validate_raw_output(
    base_url: str,
    raw_output: str,
    language: str = "ENGLISH",
    has_documents: bool = True,
) -> dict:
    """
    Validate raw LLM output text.

    Args:
        base_url: API base URL
        raw_output: Raw LLM response text
        language: Expected language
        has_documents: Whether documents were provided

    Returns:
        Validation response (same as validate_trace)
    """
    url = f"{base_url}/v2/validate"

    payload = {
        "raw_output": raw_output,
        "language": language,
        "has_documents": has_documents,
    }

    response = requests.post(url, json=payload, timeout=30)
    response.raise_for_status()
    return response.json()


def print_separator(title: str = ""):
    """Print a separator line."""
    if title:
        print(f"\n{'='*60}")
        print(f" {title}")
        print(f"{'='*60}")
    else:
        print(f"\n{'-'*60}")


def main():
    """Main entry point."""
    args = parse_args()

    # 1. Health check
    print_separator("Health Check")
    try:
        health = health_check(args.base_url)
        print(f"Status: {health['status']}")
        print(f"Version: {health['version']}")
        print(f"Models Available: {health['models_available']}")
    except requests.exceptions.ConnectionError:
        print(f"Error: Cannot connect to {args.base_url}")
        print("Make sure the API server is running.")
        sys.exit(1)

    # 2. Run agent
    print_separator("Running Agent")
    print(f"Document: {args.doc_path}")
    print(f"Query: {args.query}")
    print(f"Language: {args.lang}")
    print()

    try:
        result = run_agent(
            base_url=args.base_url,
            doc_json_path=args.doc_path,
            user_query=args.query,
            lang=args.lang,
            doc_json_path_2=args.doc_path_2,
            return_trace=args.trace,
            return_train_sample=args.train_sample,
            n_steps_max=args.max_steps,
        )
    except requests.exceptions.HTTPError as e:
        print(f"Error: {e}")
        if e.response is not None:
            print(f"Details: {e.response.text}")
        sys.exit(1)

    # 3. Print results
    print_separator("Final Answer")
    print(result["final_answer"])

    print_separator("Reasoning Steps")
    for step in result["steps_reasoning"]:
        action_str = ""
        if step.get("action"):
            action_str = f" -> {step['action']['name']}"
        print(f"  [{step['step_number']}] {step['step_type']}: {step['step_name']}{action_str}")
        print(f"       Duration: {step['duration']:.2f}s")

    print_separator("Session Info")
    print(f"Session ID: {result['session_id']}")
    print(f"Success: {result['success']}")
    print(f"Total Tokens: {result['total_tokens']}")
    print(f"Inputs Used: {result['inputs_used']}")

    if result.get("warnings"):
        print_separator("Validation Warnings")
        for warning in result["warnings"]:
            print(f"  - {warning}")

    # 4. Validate trace if requested
    if args.validate and result.get("trace"):
        print_separator("Validation")
        validation = validate_trace(
            base_url=args.base_url,
            trace=result["trace"],
            language=args.lang,
            has_documents=True,
        )

        print(f"Valid: {validation['ok']}")
        print(f"Stats: {json.dumps(validation['stats'], indent=2)}")

        if validation.get("errors"):
            print("Errors:")
            for error in validation["errors"]:
                print(f"  - {error}")

        if validation.get("warnings"):
            print("Warnings:")
            for warning in validation["warnings"]:
                print(f"  - {warning}")

    # 5. Show trace if requested
    if args.trace and result.get("trace"):
        print_separator("Full Trace")
        print(json.dumps(result["trace"], indent=2, ensure_ascii=False)[:5000])
        if len(json.dumps(result["trace"])) > 5000:
            print("... (truncated)")

    # 6. Show train_sample if requested
    if args.train_sample and result.get("train_sample"):
        print_separator("Train Sample")
        sample = result["train_sample"]
        print(f"Fields: {list(sample.keys())}")
        print(f"Reasoning steps: {len(sample.get('reasoning', []))}")
        print(f"ReadFullDocument calls: {len(sample.get('readfulldocument', []))}")
        print(f"ReadFullText calls: {len(sample.get('readfulltext', []))}")


if __name__ == "__main__":
    main()
