"""
exaone/cli.py — CLI runner for ExaoneAgent.

Usage:
    python exaone/cli.py "LG AI Research 검색해줘"
    python exaone/cli.py "query" --qa_mode=research
    python exaone/cli.py "query" --toolset=web_search --reasoning=false
    python exaone/cli.py "follow-up" --history_file=history.json
    python exaone/cli.py "follow-up" --history_json='[{"role":"user","content":"..."}]'
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from exaone.config import bootstrap_gateway_env
from exaone.agent import ExaoneAgent


def _normalize_history(raw: Any) -> List[Dict[str, Any]]:
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return []
        raw = json.loads(raw)
    if not isinstance(raw, list):
        raise ValueError("history must be a list of message dicts")
    out: List[Dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("each history item must be a dict")
        if not isinstance(item.get("role"), str):
            raise ValueError("each history item must include string 'role'")
        msg = dict(item)
        if "content" not in msg:
            msg["content"] = ""
        out.append(msg)
    return out


def _load_history(
    conversation_history: Any = None,
    history_json: Optional[str] = None,
    history_file: Optional[str] = None,
) -> List[Dict[str, Any]]:
    if conversation_history is not None:
        return _normalize_history(conversation_history)
    if history_json:
        return _normalize_history(history_json)
    if history_file:
        payload = Path(history_file).read_text(encoding="utf-8")
        return _normalize_history(payload)
    return []


def main(
    query: str,
    qa_mode: str = None,
    toolset=None,
    enabled_toolsets=None,
    reasoning: bool = True,
    verbose: bool = False,
    max_iterations: int = 10,
    conversation_history: Any = None,
    history_json: str = None,
    history_file: str = None,
):
    if isinstance(reasoning, str):
        reasoning = reasoning.lower() not in ("false", "0", "no", "off")

    bootstrap_gateway_env()
    
    agent = ExaoneAgent(
        qa_mode=qa_mode,
        toolset=toolset,
        enabled_toolsets=enabled_toolsets,
        reasoning=reasoning,
        verbose_logging=verbose,
        max_iterations=max_iterations,
    )
    history = _load_history(
        conversation_history=conversation_history,
        history_json=history_json,
        history_file=history_file,
    )
    result = agent.run_conversation(query, conversation_history=history)
    print(result.get("final_response", ""))


if __name__ == "__main__":
    import fire

    fire.Fire(main)
