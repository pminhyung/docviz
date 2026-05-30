import json

from exaone.config import (
    ExaoneConfig,
    bootstrap_gateway_env,
    is_exaone_agent_enabled,
    load_config,
    resolve_exaone_model,
    resolve_exaone_runtime_kwargs,
)


def test_bootstrap_gateway_env_sets_flags(monkeypatch, tmp_path):
    load_config.cache_clear()
    monkeypatch.delenv("HERMES_EXAONE_AGENT", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("EXAONE_MODEL=from-dotenv\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    import exaone.config as cfg_mod

    monkeypatch.setattr(cfg_mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(cfg_mod, "EXAONE_REPO_ROOT", tmp_path)
    bootstrap_gateway_env(load_dotenv=False)
    import os

    assert os.environ["HERMES_EXAONE_AGENT"] == "1"
    assert os.environ["API_SERVER_ENABLED"] == "1"


def test_load_config_is_cached(monkeypatch):
    load_config.cache_clear()
    monkeypatch.setenv("EXAONE_MODEL", "model-a")
    cfg1 = load_config()
    monkeypatch.setenv("EXAONE_MODEL", "model-b")
    cfg2 = load_config()
    assert cfg1 is cfg2  # same object — cache hit


def test_load_config_cache_clear_reloads(monkeypatch):
    load_config.cache_clear()
    monkeypatch.setenv("EXAONE_MODEL", "model-a")
    cfg1 = load_config()
    load_config.cache_clear()
    monkeypatch.setenv("EXAONE_MODEL", "model-b")
    cfg2 = load_config()
    assert cfg1.model != cfg2.model


def test_vllm_params_fallback_to_exaone_vllm_params(monkeypatch):
    load_config.cache_clear()
    monkeypatch.delenv("VLLM_PARAMS_K_EXAONE", raising=False)
    monkeypatch.setenv("EXAONE_VLLM_PARAMS", '{"temperature": 0.7}')
    cfg = ExaoneConfig.from_env()
    assert cfg.vllm_params.get("temperature") == 0.7


def test_vllm_params_invalid_json_ignored(monkeypatch):
    load_config.cache_clear()
    monkeypatch.setenv("VLLM_PARAMS_K_EXAONE", "not-json{{{")
    cfg = ExaoneConfig.from_env()
    assert cfg.vllm_params == {}


# --- apply_agent_kwargs ---

def test_apply_agent_kwargs_only_fills_missing():
    cfg = ExaoneConfig(
        enabled=True,
        hermes_home="/tmp/.hermes",
        trace_dir="/tmp/traces",
        base_url="http://vllm/v1",
        model="M1",
        api_key="k",
    )
    out = cfg.apply_agent_kwargs({"model": "override", "max_iterations": 5})
    assert out["model"] == "override"
    assert out["base_url"] == "http://vllm/v1"
    assert out["max_iterations"] == 5


def test_apply_agent_kwargs_applies_vllm_params_defaults(monkeypatch):
    load_config.cache_clear()
    monkeypatch.setenv(
        "VLLM_PARAMS_K_EXAONE",
        json.dumps({
            "max_tokens": 15000,
            "temperature": 1.0,
            "top_p": 0.95,
            "seed": 100000,
            "extra_body": {"chat_template_kwargs": {"enable_thinking": True}},
            "inputs_format": "string",
        }),
    )
    cfg = ExaoneConfig.from_env()
    out = cfg.apply_agent_kwargs({})
    assert out["max_tokens"] == 15000
    assert out["request_overrides"]["temperature"] == 1.0
    assert out["request_overrides"]["top_p"] == 0.95
    assert out["request_overrides"]["seed"] == 100000
    assert out["request_overrides"]["extra_body"]["chat_template_kwargs"]["enable_thinking"] is True
    assert out["request_overrides"]["extra_body"]["inputs_format"] == "string"


def test_apply_agent_kwargs_explicit_overrides_vllm_params(monkeypatch):
    load_config.cache_clear()
    monkeypatch.setenv(
        "VLLM_PARAMS_K_EXAONE",
        '{"max_tokens":15000,"temperature":1.0,"top_p":0.95}',
    )
    cfg = ExaoneConfig.from_env()
    out = cfg.apply_agent_kwargs({"max_tokens": 7777, "request_overrides": {"temperature": 0.2}})
    assert out["max_tokens"] == 7777
    assert out["request_overrides"]["temperature"] == 0.2
    assert out["request_overrides"]["top_p"] == 0.95


def test_apply_agent_kwargs_merges_extra_body(monkeypatch):
    load_config.cache_clear()
    monkeypatch.setenv(
        "VLLM_PARAMS_K_EXAONE",
        '{"extra_body":{"chat_template_kwargs":{"enable_thinking":true},"inputs_format":"string"}}',
    )
    cfg = ExaoneConfig.from_env()
    out = cfg.apply_agent_kwargs({
        "request_overrides": {
            "extra_body": {
                "chat_template_kwargs": {"enable_thinking": False},
                "top_k": 1,
            }
        }
    })
    extra = out["request_overrides"]["extra_body"]
    assert extra["inputs_format"] == "string"
    assert extra["top_k"] == 1
    assert extra["chat_template_kwargs"]["enable_thinking"] is False


# --- runtime kwargs ---

def test_exaone_runtime_kwargs_from_env(monkeypatch):
    load_config.cache_clear()
    monkeypatch.setenv("HERMES_EXAONE_AGENT", "1")
    monkeypatch.setenv("EXAONE_BASE_URL", "http://vllm:8000/v1")
    monkeypatch.setenv("EXAONE_API_KEY", "EMPTY")
    monkeypatch.setenv("EXAONE_MODEL", "Qwen3.5-397B-A17B-FP8")
    kw = resolve_exaone_runtime_kwargs()
    assert kw["base_url"] == "http://vllm:8000/v1"
    assert kw["api_key"] == "EMPTY"
    assert kw["provider"] == "custom"
    assert kw["api_mode"] == "chat_completions"
    assert resolve_exaone_model() == "Qwen3.5-397B-A17B-FP8"
    assert is_exaone_agent_enabled() is True
