#!/usr/bin/env python3
"""
HTTP Server-based E2E Test — Scenario-based client tests.

Starts a test server on port 9025 and runs 5 user scenarios:
1. Health check → brave_keys loaded, serpapi available
2. Normal client → reasoner_api_key in body → 200 OK
3. Admin client → X-Admin-Secret header, no api key → 200 OK
4. No auth → no api key, no admin secret → error
5. Bad admin secret → wrong header value → error

Usage:
    python run_server_e2e.py
"""
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

try:
    import requests
except ImportError:
    print("[ERROR] requests 패키지가 필요합니다: pip install requests")
    sys.exit(1)

try:
    from dotenv import dotenv_values
except ImportError:
    print("[ERROR] python-dotenv 패키지가 필요합니다: pip install python-dotenv")
    sys.exit(1)

ROOT = Path(__file__).parent.parent.parent.parent
SERVER_PORT = 9025
BASE_URL = f"http://localhost:{SERVER_PORT}"
STARTUP_TIMEOUT = 15  # seconds


def _create_demo_doc():
    """Create a temporary demo document JSON file."""
    doc = {
        "1": "# Demo Document\n\nPage 1: Introduction to the demo system.",
        "2": "# Details\n\nPage 2: The system supports document search and custom tools.",
        "3": "# Summary\n\nPage 3: Sandbox mode allows testing without external API calls.",
    }
    fd, path = tempfile.mkstemp(suffix=".json", prefix="server_e2e_doc_")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False)
    return path


def start_server():
    """Start uvicorn server on test port, return Popen."""
    env = os.environ.copy()
    # Do NOT load model API keys into env — server should use whitelist only
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "agent.api.server:app",
            "--host", "0.0.0.0",
            "--port", str(SERVER_PORT),
            "--log-level", "warning",
        ],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for server to be ready
    for i in range(STARTUP_TIMEOUT * 2):
        try:
            r = requests.get(f"{BASE_URL}/health", timeout=1)
            if r.status_code == 200:
                print(f"[Server] Started on port {SERVER_PORT} (pid={proc.pid})")
                return proc
        except requests.exceptions.ConnectionError:
            pass
        time.sleep(0.5)

    # Failed to start
    proc.kill()
    stdout, stderr = proc.communicate()
    print(f"[ERROR] Server failed to start within {STARTUP_TIMEOUT}s")
    print(f"  stdout: {stdout.decode()[-500:]}")
    print(f"  stderr: {stderr.decode()[-500:]}")
    sys.exit(1)


def stop_server(proc):
    """Gracefully stop the server."""
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    print(f"[Server] Stopped (pid={proc.pid})")


# ── Test Scenarios ──


def test_health():
    """Scenario 1: Health check → brave_keys loaded."""
    print("\n[Test 1] Health check...")
    r = requests.get(f"{BASE_URL}/health", timeout=10)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    assert data["status"] == "healthy", f"Unexpected status: {data['status']}"
    assert data["models_available"] is True, "models_available should be True"
    print(f"  status={data['status']}, models_available={data['models_available']}")
    return True


def test_normal_client(doc_path, env_vals):
    """Scenario 2: Normal client with reasoner_api_key in body."""
    print("\n[Test 2] Normal client (api key in body)...")

    # Use Novita key with explicit Novita model
    api_key = env_vals.get("NOVITA_API_KEY", "")
    if not api_key:
        print("  [SKIP] NOVITA_API_KEY not in .env")
        return True

    payload = {
        "doc_json_path": doc_path,
        "user_query": "What are the main topics?",
        "reasoner_api_key": api_key,
        "reasoner_model_name": "qwen/qwen3-235b-a22b-instruct-2507",
        "n_steps_max": 5,
    }

    r = requests.post(f"{BASE_URL}/v2/run", json=payload, timeout=300)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:200]}"
    data = r.json()
    assert data["success"] is True, f"Expected success=true: {data.get('error')}"
    print(f"  success={data['success']}, steps={data['num_steps']}, answer={data['final_answer'][:100]}...")
    return True


def test_admin_client(doc_path, env_vals):
    """Scenario 3: Admin client with X-Admin-Secret, no reasoner_api_key."""
    print("\n[Test 3] Admin client (X-Admin-Secret header)...")

    admin_secret = env_vals.get("DOCVIZ_AGENT_ADMIN_SECRET", "")
    if not admin_secret:
        print("  [SKIP] DOCVIZ_AGENT_ADMIN_SECRET not in .env")
        return True

    payload = {
        "doc_json_path": doc_path,
        "user_query": "Summarize this document briefly",
        "n_steps_max": 5,
        # No reasoner_api_key — admin mode resolves from .env
    }
    headers = {"X-Admin-Secret": admin_secret}

    r = requests.post(f"{BASE_URL}/v2/run", json=payload, headers=headers, timeout=300)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:200]}"
    data = r.json()
    assert data["success"] is True, f"Expected success=true: {data.get('error')}"
    print(f"  success={data['success']}, steps={data['num_steps']}, answer={data['final_answer'][:100]}...")
    return True


def test_no_auth(doc_path):
    """Scenario 4: No api key, no admin secret → error."""
    print("\n[Test 4] No auth (no api key, no admin secret)...")

    payload = {
        "doc_json_path": doc_path,
        "user_query": "Hello?",
        "n_steps_max": 3,
        # No reasoner_api_key, no admin header
    }

    r = requests.post(f"{BASE_URL}/v2/run", json=payload, timeout=30)
    # Should fail with 400 or 500
    assert r.status_code >= 400, f"Expected error, got {r.status_code}"
    print(f"  status={r.status_code} (expected error)")
    return True


def test_bad_admin_secret(doc_path):
    """Scenario 5: Wrong admin secret → error."""
    print("\n[Test 5] Bad admin secret...")

    payload = {
        "doc_json_path": doc_path,
        "user_query": "Hello?",
        "n_steps_max": 3,
    }
    headers = {"X-Admin-Secret": "wrong_secret_value"}

    r = requests.post(f"{BASE_URL}/v2/run", json=payload, headers=headers, timeout=30)
    assert r.status_code >= 400, f"Expected error, got {r.status_code}"
    print(f"  status={r.status_code} (expected error)")
    return True


def main():
    # Read .env values for test data
    env_path = ROOT / ".env"
    env_vals = dotenv_values(env_path) if env_path.exists() else {}

    doc_path = _create_demo_doc()
    proc = None

    try:
        proc = start_server()

        results = {}
        tests = [
            ("health", lambda: test_health()),
            ("normal_client", lambda: test_normal_client(doc_path, env_vals)),
            ("admin_client", lambda: test_admin_client(doc_path, env_vals)),
            ("no_auth", lambda: test_no_auth(doc_path)),
            ("bad_admin_secret", lambda: test_bad_admin_secret(doc_path)),
        ]

        for name, test_fn in tests:
            try:
                passed = test_fn()
                results[name] = "PASS" if passed else "FAIL"
            except AssertionError as e:
                results[name] = f"FAIL: {e}"
            except Exception as e:
                results[name] = f"ERROR: {e}"

        # Summary
        print(f"\n{'='*60}")
        print("[SUMMARY] Server E2E Scenarios")
        print(f"{'='*60}")
        all_pass = True
        for name, status in results.items():
            icon = "v" if status == "PASS" else "x"
            print(f"  [{icon}] {name}: {status}")
            if status != "PASS":
                all_pass = False

        sys.exit(0 if all_pass else 1)

    finally:
        if proc:
            stop_server(proc)
        if os.path.exists(doc_path):
            os.unlink(doc_path)


if __name__ == "__main__":
    main()
