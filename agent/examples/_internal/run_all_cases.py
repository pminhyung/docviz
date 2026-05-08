#!/usr/bin/env python3
"""
Internal: Run all 4 use case E2E tests using .env keys.

Usage:
    # sandbox mode (no keys needed)
    DOC_AGENT_V2_SANDBOX=1 python run_all_cases.py

    # real mode (requires .env)
    python run_all_cases.py
"""
import os
import sys
import subprocess
from pathlib import Path

# Load .env from project root
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv optional, rely on environment variables

ROOT = Path(__file__).parent.parent.parent.parent
EXAMPLES = ROOT / "agent" / "examples"

CASES = [
    ("tool_vl", "run_e2e_test.py"),
    ("tool_llm", "run_e2e_test.py"),
    ("reasoner_vl_gpt", "run_e2e_test.py"),
    ("reasoner_vl_novita", "run_e2e_test.py"),
]


def main():
    is_sandbox = os.environ.get("DOC_AGENT_V2_SANDBOX", "").lower() in ("1", "true", "yes")

    if not is_sandbox:
        # Check required keys
        novita_key = os.environ.get("NOVITA_API_KEY")
        openai_key = os.environ.get("OPENAI_API_KEY")
        if not novita_key:
            print("[ERROR] .env에 NOVITA_API_KEY를 설정하세요")
            sys.exit(1)
        if not openai_key:
            print("[WARNING] OPENAI_API_KEY 미설정 — GPT 케이스 스킵 가능")

    results = {}
    for case_dir, script in CASES:
        script_path = EXAMPLES / case_dir / script
        if not script_path.exists():
            print(f"[SKIP] {case_dir}/{script} — not found")
            results[case_dir] = "SKIP"
            continue

        print(f"\n{'='*60}")
        print(f"[RUN] {case_dir}/{script}")
        print(f"{'='*60}")

        env = os.environ.copy()
        if is_sandbox:
            env["DOC_AGENT_V2_SANDBOX"] = "1"

        try:
            proc = subprocess.run(
                [sys.executable, str(script_path)],
                env=env,
                cwd=str(ROOT),
                timeout=120,
            )
            results[case_dir] = "PASS" if proc.returncode == 0 else "FAIL"
        except subprocess.TimeoutExpired:
            results[case_dir] = "TIMEOUT"
        except Exception as e:
            results[case_dir] = f"ERROR: {e}"

    print(f"\n{'='*60}")
    print("[SUMMARY]")
    print(f"{'='*60}")
    all_pass = True
    for case_dir, status in results.items():
        icon = "v" if status == "PASS" else "x"
        print(f"  [{icon}] {case_dir}: {status}")
        if status != "PASS":
            all_pass = False

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
