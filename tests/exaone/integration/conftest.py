import os
import shutil

import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "integration: marks tests requiring a live vLLM endpoint (EXAONE_BASE_URL)"
    )


@pytest.fixture(autouse=True)
def require_exaone_endpoint():
    try:
        from exaone.config import bootstrap_gateway_env
        bootstrap_gateway_env()
    except Exception:
        pass
    if not os.getenv("EXAONE_BASE_URL"):
        pytest.skip("EXAONE_BASE_URL not set — integration test skipped")


@pytest.fixture(autouse=True)
def _cleanup_integration_traces(monkeypatch):
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
