"""Code execution tool for ExaoneAgent — delegates to the gw-dev code execution endpoint.

The handler forwards the user-supplied Python snippet to an external
``code_execute`` endpoint that runs it server-side and returns captured
``stdout`` / ``stderr``. The remote runtime understands both plain
``print(...)`` output AND trailing-expression return values (REPL style),
so the model can use either style.
"""

import httpx

from tools.registry import registry, tool_result


_CODE_EXECUTION_URL = "http://gw-dev.lgair.net/api/lang/chat-exaone/code"
_TIMEOUT_SECONDS = 60.0


CODE_TOOL_SCHEMA = {
    "name": "code_tool",
    "description": "Execute a Python code snippet and return captured stdout/stderr.",
    "parameters": {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": (
                    "Python code to execute. Self-contained — put imports at the top. "
                    "Both `print(...)` output and the trailing expression value are captured."
                ),
            },
        },
        "required": ["code"],
    },
}


def _format_stdout(stdout_items) -> str:
    """Join the remote ``stdout`` list (``[{type, value}, ...]``) into a single string.

    The remote runtime emits two entry types:
      - ``type=print``  → ``value`` is the printed text (already includes ``\\n``)
      - ``type=return`` → ``value`` is the raw object of a trailing expression
                          (int/float/None/etc.), no trailing newline

    Non-string values are stringified and a newline is appended so successive
    entries don't run together.
    """
    if not isinstance(stdout_items, list):
        return ""
    parts: list[str] = []
    for item in stdout_items:
        if not isinstance(item, dict):
            continue
        v = item.get("value", "")
        if isinstance(v, str):
            parts.append(v)
        else:
            parts.append(f"{str(v)}\n")
    return "".join(parts)


def _code_tool_handler(args: dict | None = None, **_kwargs) -> str:
    code = (args or {}).get("code", "")

    request_body = {
        "inputs": [{"messages": [{"role": "user", "content": code}]}],
        "params": {
            "inputs_format": "json",
            "max_tokens": 5000,
            "temperature": 0.7,
            "top_p": 0.8,
            "extra_body": {
                "top_k": 20,
                "min_p": 0,
                "chat_template_kwargs": {"enable_thinking": False},
            },
            "model": "k-exaone",
            "code_execute": True,
        },
    }

    try:
        response = httpx.post(
            _CODE_EXECUTION_URL,
            json=request_body,
            headers={"Content-Type": "application/json"},
            timeout=_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        raw = response.json()
    except httpx.TimeoutException:
        return tool_result(
            success=False,
            data={"stdout": "", "stderr": "Request timed out"},
            meta={"tool": "code_tool"},
        )
    except httpx.HTTPStatusError as exc:
        return tool_result(
            success=False,
            data={"stdout": "", "stderr": str(exc)},
            meta={"tool": "code_tool"},
        )
    except Exception as exc:
        return tool_result(
            success=False, data={"stdout": "", "stderr": str(exc)}, meta={"tool": "code_tool"}
        )

    outputs = raw.get("outputs", [])
    if not outputs:
        return tool_result(
            success=False,
            data={"stdout": "", "stderr": "no execution output"},
            meta={"tool": "code_tool"},
        )

    out = outputs[0]
    returncode = out.get("returncode", -1)
    stderr = out.get("stderr", "")
    stdout = _format_stdout(out.get("stdout", []))

    if returncode == 0:
        return tool_result(
            success=True,
            data={"stdout": stdout, "stderr": stderr},
            meta={"tool": "code_tool"},
        )
    return tool_result(
        success=False,
        data={"stdout": stdout, "stderr": stderr},
        meta={"tool": "code_tool"},
    )


registry.register(
    name="code_tool",
    toolset="code",
    schema=CODE_TOOL_SCHEMA,
    handler=_code_tool_handler,
    emoji="🐍",
)
