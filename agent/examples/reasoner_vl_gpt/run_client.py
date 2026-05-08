#!/usr/bin/env python3
"""
GPT-4o VL Reasoner Client — OpenAI API 사용.

Usage:
    python run_client.py \
        --api-key sk-proj-YOUR_OPENAI_KEY \
        --doc-json /path/to/document.json \
        --image-dir /path/to/images/ \
        --query "What are the main findings?"
"""
import argparse
import json
import sys

try:
    import requests
except ImportError:
    print("[ERROR] requests 패키지가 필요합니다: pip install requests")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="GPT VL Reasoner Client")
    parser.add_argument("--api-key", required=True, help="OpenAI API key (sk-proj-...)")
    parser.add_argument("--doc-json", required=True, help="Path to document JSON file")
    parser.add_argument("--image-dir", default=None, help="Path to page image directory")
    parser.add_argument("--query", default="What are the main findings in this document?", help="User query")
    parser.add_argument("--server-url", default="http://localhost:8000", help="API server URL")
    parser.add_argument("--session-id", default=None, help="Session ID for sample accumulation")
    parser.add_argument("--lang", default="en", choices=["en", "ko"], help="Output language")
    parser.add_argument("--output", default=None, help="Save response to JSON file")
    args = parser.parse_args()

    if not args.api_key:
        print("[ERROR] --api-key 필수. OpenAI API 키를 전달하세요.")
        sys.exit(1)

    payload = {
        "doc_json_path": args.doc_json,
        "user_query": args.query,
        "lang": args.lang,
        "reasoner_type": "vl",
        "reasoner_model_name": "gpt-4o",
        "reasoner_api_key": args.api_key,
        "return_train_sample": True,
    }

    if args.image_dir:
        payload["doc_image_dir"] = args.image_dir
    if args.session_id:
        payload["session_id"] = args.session_id

    print(f"[Client] GPT-4o VL Reasoner")
    print(f"[Client] Sending request to {args.server_url}/v2/run")
    print(f"[Client] Query: {args.query}")

    try:
        resp = requests.post(f"{args.server_url}/v2/run", json=payload, timeout=300)
        resp.raise_for_status()
        data = resp.json()

        print(f"\n{'='*60}")
        print(f"[Result] Success: {data.get('success')}")
        print(f"[Result] Steps: {data.get('num_steps')}")
        print(f"[Result] Tokens: {data.get('total_tokens')}")
        print(f"\n--- Final Answer ---")
        print(data.get("final_answer", "(no answer)"))

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"\n[Client] Response saved to {args.output}")

    except requests.exceptions.ConnectionError:
        print(f"[ERROR] Cannot connect to {args.server_url}. Is the server running?")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
