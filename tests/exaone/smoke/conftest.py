import os
import shutil

import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "smoke: marks tests requiring a live vLLM endpoint (EXAONE_BASE_URL)"
    )


@pytest.fixture(autouse=True)
def require_exaone_endpoint():
    # Load .env so EXAONE_BASE_URL is visible even if not shell-exported.
    try:
        from exaone.config import bootstrap_gateway_env
        bootstrap_gateway_env()
    except Exception:
        pass
    if not os.getenv("EXAONE_BASE_URL"):
        pytest.skip("EXAONE_BASE_URL not set — smoke test skipped")


@pytest.fixture(autouse=True)
def _enforce_test_timeout():
    """Override root conftest's 30s timeout — smoke tests need more time for LLM calls."""
    yield


@pytest.fixture(autouse=True)
def _cleanup_smoke_traces(monkeypatch):
    """Delete only the run_dirs created by this test's ExaoneAgent instances.

    Patches run_conversation to record each _current_run_dir so parallel tests
    never accidentally delete each other's trace directories.
    """
    from exaone.agent import ExaoneAgent

    created_dirs = []
    original = ExaoneAgent.run_conversation

    def _tracking(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        if hasattr(self, "_current_run_dir"):
            created_dirs.append(self._current_run_dir)
        return result

    monkeypatch.setattr(ExaoneAgent, "run_conversation", _tracking)
    yield
    for d in created_dirs:
        shutil.rmtree(d, ignore_errors=True)
