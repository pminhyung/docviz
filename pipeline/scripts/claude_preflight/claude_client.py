"""Subprocess wrapper around `claude -p` for VisuBench preflight runs.

Uses Claude Code CLI in print mode with --output-format json to extract:
  - result text
  - input/output tokens
  - total_cost_usd
  - duration

Two entry points:
  - call_text_generation: pure text prompt (chart/diagram/mindmap generation)
  - call_vision_judge: judge a PNG via the Read tool (tool-use roundtrip)
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ClaudeResponse:
    ok: bool
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    cost_usd: float = 0.0
    duration_s: float = 0.0
    error: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


def _run_claude(
    user_prompt: str,
    system_prompt: str,
    model: str = "sonnet",
    allowed_tools: list[str] | None = None,
    max_turns: int = 1,
    timeout: int = 300,
    cwd: str | None = None,
) -> ClaudeResponse:
    # Always pipe the user prompt through stdin:
    #   1. --allowedTools is variadic and would swallow trailing positional args.
    #   2. Long prompts (>>argv limit) or prompts containing NULL bytes break
    #      subprocess argv transport.
    # Sanitize the payload before sending — remove NULs and normalize CR.
    safe_prompt = user_prompt.replace("\x00", "").replace("\r\n", "\n")
    cmd = [
        "claude", "-p",
        "--model", model,
        "--output-format", "json",
        "--system-prompt", system_prompt,
        "--max-turns", str(max_turns),
    ]
    if allowed_tools:
        cmd += ["--allowedTools", *allowed_tools]
    stdin_input = safe_prompt

    env = os.environ.copy()
    env["CLAUDE_CODE_NON_INTERACTIVE"] = "1"
    start = time.time()
    try:
        proc = subprocess.run(
            cmd,
            input=stdin_input,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            cwd=cwd,
        )
    except subprocess.TimeoutExpired:
        return ClaudeResponse(ok=False, text="", duration_s=time.time() - start, error="timeout")
    duration = time.time() - start

    if proc.returncode != 0 and not proc.stdout.strip():
        return ClaudeResponse(
            ok=False, text="", duration_s=duration,
            error=f"returncode={proc.returncode}; stderr={proc.stderr[:400]}",
        )

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        return ClaudeResponse(
            ok=False, text=proc.stdout[:400], duration_s=duration,
            error=f"json_decode_error: {e}",
        )

    is_error = data.get("is_error", False)
    result = data.get("result") or ""
    usage = data.get("usage") or {}
    return ClaudeResponse(
        ok=not is_error,
        text=str(result),
        input_tokens=int(usage.get("input_tokens") or 0),
        output_tokens=int(usage.get("output_tokens") or 0),
        cache_creation_tokens=int(usage.get("cache_creation_input_tokens") or 0),
        cache_read_tokens=int(usage.get("cache_read_input_tokens") or 0),
        cost_usd=float(data.get("total_cost_usd") or 0.0),
        duration_s=duration,
        error="" if not is_error else str(result)[:200],
        raw=data,
    )


def call_text_generation(
    user_content: str,
    system_prompt: str,
    model: str = "sonnet",
    timeout: int = 180,
) -> ClaudeResponse:
    """Call Claude for a text-only generation (chart/diagram/mindmap)."""
    return _run_claude(
        user_prompt=user_content,
        system_prompt=system_prompt,
        model=model,
        allowed_tools=None,
        max_turns=1,
        timeout=timeout,
    )


_HUMAN_EVAL_SYSTEM = (
    "You are simulating an expert human annotator for a benchmark of "
    "automatically-generated information visualizations. You will receive "
    "(1) an excerpt from a source document and (2) a rendered visualization image. "
    "Rate the visualization on FOUR independent axes using a 1–5 Likert scale "
    "(1 = very poor, 5 = excellent). Be strict but fair, exactly as a human reviewer "
    "filling in our annotation web form would be. "
    "Output ONLY a single JSON object with EXACTLY these keys: "
    '"struct", "clarity", "faith", "overall", "rationale". '
    "No markdown code fences, no preamble, no explanation outside the JSON."
)


def _human_eval_user_prompt(image_path: str, doc_excerpt: str, viz_type: str) -> str:
    return (
        f"Please Read the following image: {image_path}\n\n"
        f"Visualization type: {viz_type}\n\n"
        f"Document excerpt (truncated):\n---\n{doc_excerpt[:4000]}\n---\n\n"
        "Rate the visualization on these FOUR axes (1–5 Likert each):\n"
        "- struct (Structural Correctness): Does the visualization encode the document's "
        "key entities/relations correctly? Are nodes/edges/data values right? "
        "(5 = perfect, 1 = wrong structure)\n"
        "- clarity (Visual Clarity): Is the layout legible, well-organized, free of "
        "overlapping/cluttered/truncated elements? (5 = very clear, 1 = illegible)\n"
        "- faith (Faithfulness): Does the visualization avoid hallucinations or content "
        "not present in the source? (5 = fully faithful, 1 = hallucinated)\n"
        "- overall (Overall Quality): Your holistic judgment of acceptability. "
        "(5 = excellent, 1 = unusable)\n\n"
        "Return one JSON object. Example:\n"
        '{"struct": 4, "clarity": 3, "faith": 5, "overall": 4, '
        '"rationale": "<one sentence why>"}'
    )


def call_human_eval_simulation(
    image_path: str,
    doc_excerpt: str,
    viz_type: str,
    model: str = "opus",
    timeout: int = 300,
) -> ClaudeResponse:
    """Call Claude (default Opus) to simulate a human annotator on the
    Phase B 4-dimension Likert rubric."""
    return _run_claude(
        user_prompt=_human_eval_user_prompt(image_path, doc_excerpt, viz_type),
        system_prompt=_HUMAN_EVAL_SYSTEM,
        model=model,
        allowed_tools=["Read"],
        max_turns=3,
        timeout=timeout,
    )


def call_vision_judge(
    image_path: str,
    doc_excerpt: str,
    viz_type: str,
    model: str = "sonnet",
    timeout: int = 240,
) -> ClaudeResponse:
    """Call Claude to judge a rendered viz PNG via the Read tool.

    The Read tool natively handles PNG → base64 inline image input.
    """
    system_prompt = (
        "You are an expert evaluator of automatically-generated information visualizations. "
        "You will be given (1) a short document excerpt and (2) a rendered visualization image. "
        "Rate the visualization on three axes using a 1–5 Likert scale "
        "(1 = very poor, 5 = excellent). "
        "Output ONLY a single JSON object with exactly these keys: "
        '"faithfulness", "clarity", "overall", "rationale". '
        "Do not include any markdown fences, preamble, or explanation outside the JSON."
    )
    user_prompt = (
        f"Please Read the following image: {image_path}\n\n"
        f"Visualization type: {viz_type}\n\n"
        f"Document excerpt (truncated):\n---\n{doc_excerpt[:4000]}\n---\n\n"
        "Rating criteria (1–5 each):\n"
        "- faithfulness: Does the visualization accurately reflect content from the document? "
        "(5 = fully faithful, 1 = hallucinated or contradictory)\n"
        "- clarity: Is the visualization legible, well-organized, and free of overlapping/cluttered elements? "
        "(5 = very clear, 1 = illegible)\n"
        "- overall: Your holistic judgment of acceptability. "
        "(5 = excellent, 1 = unusable)\n\n"
        "Return a single JSON object. Example: "
        '{"faithfulness": 4, "clarity": 3, "overall": 4, "rationale": "<one sentence>"}'
    )
    return _run_claude(
        user_prompt=user_prompt,
        system_prompt=system_prompt,
        model=model,
        allowed_tools=["Read"],
        max_turns=3,
        timeout=timeout,
    )
