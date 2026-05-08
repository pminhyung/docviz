#!/usr/bin/env python3
"""
Mindmap Tool Demo Quality Test.

Runs demo queries against real documents via agent API,
then verifies output quality (tools used, files generated, file sizes).

Prerequisites:
    1. mindmap-renderer sidecar running on :3004
    2. agent API server running (default port 9025)
    3. .env loaded with API keys

Usage:
    set -a; source .env; set +a
    python -m agent.examples.mindmap.run_demo_test

    # Single query
    python -m agent.examples.mindmap.run_demo_test --query 1

    # Custom port
    python -m agent.examples.mindmap.run_demo_test --port 9024
"""
import argparse
import glob
import json
import os
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    print("[ERROR] requests library required: pip install requests")
    sys.exit(1)


# ── Configuration ──────────────────────────────────────────────────

ADMIN_SECRET = os.environ.get(
    "DOCVIZ_AGENT_ADMIN_SECRET", "docviz_agent_internal_secret_2026"
)
OUTPUT_DIR = "/tmp/mindmap_demo_output"
TOOLS_PATH = str(Path(__file__).parent / "mindmap_tools.py")
DOCAI_BASE = "/ex_disk2/mhpark/poc/docai/out"

CUSTOM_RULES = """- You MUST use generate_mindmap tool when asked to create a mindmap, knowledge map, or topic hierarchy.
- Before calling generate_mindmap, search/read the document to gather context.
- Include cross-reference links between related topics (show_cross_links=true).
- Always report the file_path of generated output files in your final answer.
- Do NOT just list topics textually — use generate_mindmap to create an actual interactive mindmap file."""


# ── Demo Queries ───────────────────────────────────────────────────

QUERIES = [
    {
        "id": 1,
        "name": "Mindmap - Korean Financial Document",
        "doc_json_path": f"{DOCAI_BASE}/32_IM증권/00163f84.json",
        "doc_image_dir": f"{DOCAI_BASE}/img/32_IM증권/00163f84/",
        "user_query": (
            "이 문서의 핵심 내용을 마인드맵으로 정리해주세요. "
            "generate_mindmap 도구를 사용하여 corporate 테마로 생성해주세요."
        ),
        "lang": "ko",
        "reasoner_type": "llm",
        "expected_tools": ["generate_mindmap"],
        "expected_outputs": ["mindmap_*.html"],
        "min_file_size": 50000,
        "tool_args": {"theme": "corporate", "output_format": "html"},
    },
    {
        "id": 2,
        "name": "Mindmap - Focus Mode + Dark Theme",
        "doc_json_path": f"{DOCAI_BASE}/32_IM증권/00163f84.json",
        "doc_image_dir": f"{DOCAI_BASE}/img/32_IM증권/00163f84/",
        "user_query": (
            "이 문서에서 재무 성과(매출, 영업이익)에 관한 내용만 집중해서 "
            "마인드맵을 생성해주세요. generate_mindmap 도구를 사용하되 "
            "focus_query='재무 성과 분석', theme='dark', show_cross_links=true로 설정해주세요."
        ),
        "lang": "ko",
        "reasoner_type": "llm",
        "expected_tools": ["generate_mindmap"],
        "expected_outputs": ["mindmap_*.html"],
        "min_file_size": 50000,
        "tool_args": {"focus_query": "재무 성과 분석", "theme": "dark"},
    },
    {
        "id": 3,
        "name": "Mindmap - HTML + PNG Export",
        "doc_json_path": f"{DOCAI_BASE}/32_IM증권/00163f84.json",
        "doc_image_dir": f"{DOCAI_BASE}/img/32_IM증권/00163f84/",
        "user_query": (
            "이 문서를 분석하고 generate_mindmap 도구로 마인드맵을 생성해주세요. "
            "output_format='all', theme='academic', layout='tree_lr' 로 설정해주세요."
        ),
        "lang": "ko",
        "reasoner_type": "llm",
        "expected_tools": ["generate_mindmap"],
        "expected_outputs": ["mindmap_*.html"],
        "min_file_size": 50000,
        "tool_args": {"output_format": "all", "theme": "academic", "layout": "tree_lr"},
    },
    # ── Feature 1: Focus Query Deep Sub-Mindmap ──
    {
        "id": 4,
        "name": "Focus Deep Dive - 투자 리스크 분석",
        "doc_json_path": f"{DOCAI_BASE}/32_IM증권/00163f84.json",
        "doc_image_dir": f"{DOCAI_BASE}/img/32_IM증권/00163f84/",
        "user_query": (
            "이 증권 보고서에서 '투자 리스크와 향후 전망'에 대해서만 "
            "깊이 있는 마인드맵을 만들어주세요. 일반적인 문서 요약이 아니라, "
            "리스크 요인별 구체적 근거와 영향도를 포함해야 합니다. "
            "generate_mindmap 도구를 사용하되 "
            "focus_query='투자 리스크 요인과 향후 전망 분석', "
            "depth=4, theme='dark', show_cross_links=true로 설정해주세요."
        ),
        "lang": "ko",
        "reasoner_type": "llm",
        "expected_tools": ["generate_mindmap"],
        "expected_outputs": ["mindmap_*.html"],
        "min_file_size": 50000,
        "tool_args": {
            "focus_query": "투자 리스크 요인과 향후 전망 분석",
            "depth": 4,
            "theme": "dark",
            "show_cross_links": True,
        },
    },
    # ── Feature 2: Multi-Document Cross-Reference Mindmap ──
    {
        "id": 5,
        "name": "Cross-Document - 증권사 리포트 비교 분석",
        "doc_json_path": f"{DOCAI_BASE}/32_IM증권/00163f84.json",
        "doc_json_path_2": f"{DOCAI_BASE}/32_IM증권/002e5710.json",
        "doc_image_dir": f"{DOCAI_BASE}/img/32_IM증권/00163f84/",
        "user_query": (
            "두 증권사 리포트의 공통 주제와 상이한 관점을 비교 분석하는 "
            "마인드맵을 생성해주세요. 각 문서에서 나온 주제 간의 관계를 "
            "cross-reference 링크로 시각화해야 합니다. "
            "generate_mindmap 도구를 사용하되 "
            "theme='academic', show_cross_links=true, layout='radial'로 설정해주세요."
        ),
        "lang": "ko",
        "reasoner_type": "llm",
        "expected_tools": ["generate_mindmap"],
        "expected_outputs": ["mindmap_*.html"],
        "min_file_size": 50000,
        "tool_args": {
            "theme": "academic",
            "show_cross_links": True,
            "layout": "radial",
        },
        "multi_doc": True,
    },
]


# ── Runner ─────────────────────────────────────────────────────────

def run_query(query: dict, api_base: str) -> dict:
    """Send query to agent API and return response."""
    # Ensure output dir exists
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Qwen onpremise config
    qwen_host = os.environ.get("QWEN_ONPREMISE_HOST", "10.1.211.148")
    qwen_port = os.environ.get("QWEN_ONPREMISE_PORT", "8000")
    qwen_model = os.environ.get("QWEN_ONPREMISE_MODEL", "Qwen3.5-397B-A17B-FP8")

    payload = {
        "doc_json_path": query["doc_json_path"],
        "doc_image_dir": query.get("doc_image_dir"),
        "user_query": query["user_query"],
        "lang": query.get("lang", "ko"),
        "reasoner_type": query.get("reasoner_type", "llm"),
        "reasoner_model_name": qwen_model,
        "reasoner_api_key": "EMPTY",
        "reasoner_base_url": f"http://{qwen_host}:{qwen_port}/v1",
        "custom_tools_path": TOOLS_PATH,
        "custom_rules": CUSTOM_RULES,
        "tool_secrets": {
            "MINDMAP_API_URL": "http://localhost:3004",
            "OUTPUT_DIR": OUTPUT_DIR,
        },
        "n_steps_max": 15,
        "return_trace": True,
        "return_train_sample": True,
    }

    # Multi-document support: add second doc path
    if query.get("multi_doc") and query.get("doc_json_path_2"):
        payload["doc_json_path_2"] = query["doc_json_path_2"]

    start = time.time()
    resp = requests.post(
        f"{api_base}/v2/run",
        json=payload,
        headers={"X-Admin-Secret": ADMIN_SECRET},
        timeout=600,
    )
    duration = time.time() - start

    if resp.status_code != 200:
        return {"error": f"HTTP {resp.status_code}: {resp.text[:500]}", "duration": duration}

    data = resp.json()
    data["duration"] = duration
    return data


def verify_query(query: dict, result: dict) -> list:
    """Verify query results."""
    errors = []

    if result.get("error"):
        errors.append(f"API error: {result['error']}")
        return errors

    if not result.get("success"):
        errors.append(f"success=false: {result.get('error', 'unknown')}")
        return errors

    # Check tools used
    steps = result.get("steps_reasoning", [])
    tools_used = set()
    for step in steps:
        action = step.get("action") or {}
        name = action.get("name", "")
        if name:
            tools_used.add(name)

    for expected in query["expected_tools"]:
        if expected not in tools_used:
            errors.append(f"Expected tool '{expected}' not used. Used: {tools_used}")

    # Check output files
    for pattern in query["expected_outputs"]:
        matches = glob.glob(os.path.join(OUTPUT_DIR, pattern))
        if not matches:
            errors.append(f"No files matching '{pattern}' in {OUTPUT_DIR}")
        else:
            for fpath in matches:
                size = os.path.getsize(fpath)
                if size < query["min_file_size"]:
                    errors.append(f"File {fpath} too small: {size} bytes (min: {query['min_file_size']})")

    # Check final answer exists
    if not result.get("final_answer"):
        errors.append("No final_answer in response")

    return errors


# ── Main ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Mindmap Demo Test")
    parser.add_argument("--port", type=int, default=9025, help="API server port")
    parser.add_argument("--query", type=int, default=0, help="Run single query (1-3, 0=all)")
    args = parser.parse_args()

    api_base = f"http://localhost:{args.port}"

    # Pre-flight: check API server
    try:
        r = requests.get(f"{api_base}/health", timeout=5)
        print(f"[OK] API server: {r.json()}")
    except Exception as e:
        print(f"[ERROR] API server not reachable at {api_base}: {e}")
        sys.exit(1)

    # Pre-flight: check mindmap-renderer sidecar
    try:
        r = requests.get("http://localhost:3004/health", timeout=5)
        print(f"[OK] mindmap-renderer: {r.json()}")
    except Exception as e:
        print(f"[ERROR] mindmap-renderer not reachable at :3004: {e}")
        sys.exit(1)

    queries = QUERIES if args.query == 0 else [q for q in QUERIES if q["id"] == args.query]
    if not queries:
        print(f"[ERROR] Query {args.query} not found")
        sys.exit(1)

    # Clean output dir
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    results_table = []
    all_passed = True

    for q in queries:
        print(f"\n{'='*60}")
        print(f"[Q{q['id']}] {q['name']}")
        print(f"{'='*60}")

        result = run_query(q, api_base)
        errors = verify_query(q, result)

        status = "PASS" if not errors else "FAIL"
        if errors:
            all_passed = False

        tools_used = set()
        for step in result.get("steps_reasoning", []):
            action = step.get("action") or {}
            if action.get("name"):
                tools_used.add(action["name"])

        results_table.append({
            "query": q["id"],
            "name": q["name"],
            "status": status,
            "duration": f"{result.get('duration', 0):.1f}s",
            "steps": result.get("num_steps", "?"),
            "tools": ", ".join(sorted(tools_used)) or "none",
            "final_answer": (result.get("final_answer") or "")[:100],
            "errors": errors,
        })

        if errors:
            for e in errors:
                print(f"  [ERROR] {e}")
        else:
            print(f"  [PASS] {result.get('duration', 0):.1f}s, {result.get('num_steps', '?')} steps")

    # Summary
    print(f"\n{'='*60}")
    print("RESULTS SUMMARY")
    print(f"{'='*60}")
    print(f"{'Q':<4} {'Name':<35} {'Status':<6} {'Duration':<10} {'Tools'}")
    print("-" * 80)
    for r in results_table:
        print(f"Q{r['query']:<3} {r['name'][:34]:<35} {r['status']:<6} {r['duration']:<10} {r['tools']}")

    # List generated files
    print(f"\n[Output files in {OUTPUT_DIR}]")
    for f in sorted(glob.glob(os.path.join(OUTPUT_DIR, "mindmap_*"))):
        size = os.path.getsize(f)
        print(f"  {os.path.basename(f)} ({size:,} bytes)")

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
