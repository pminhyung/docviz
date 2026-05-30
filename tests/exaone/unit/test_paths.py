import os

from exaone.config import (
    EXAONE_REPO_ROOT,
    REPO_ROOT,
    apply_project_path_defaults,
    is_exaone_agent_enabled,
    project_hermes_home,
    project_trace_dir,
)


def test_project_paths_under_repo():
    assert REPO_ROOT == EXAONE_REPO_ROOT
    assert project_hermes_home() == REPO_ROOT / ".hermes"
    assert project_trace_dir() == REPO_ROOT / "logs" / "exaone_traces"


def test_apply_project_path_defaults_when_exaone_enabled(monkeypatch):
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.delenv("EXAONE_TRACE_DIR", raising=False)
    monkeypatch.setenv("HERMES_EXAONE_AGENT", "1")
    apply_project_path_defaults()
    assert os.environ["HERMES_HOME"] == str(project_hermes_home())
    assert os.environ["EXAONE_TRACE_DIR"] == str(project_trace_dir())
    assert is_exaone_agent_enabled() is True


def test_apply_project_path_defaults_overrides_existing_env_when_exaone_enabled(monkeypatch):
    monkeypatch.setenv("HERMES_HOME", "/tmp/other-hermes-home")
    monkeypatch.setenv("EXAONE_TRACE_DIR", "/tmp/other-trace-dir")
    monkeypatch.setenv("HERMES_EXAONE_AGENT", "1")

    apply_project_path_defaults()

    assert os.environ["HERMES_HOME"] == str(project_hermes_home())
    assert os.environ["EXAONE_TRACE_DIR"] == str(project_trace_dir())
