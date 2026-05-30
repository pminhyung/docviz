"""
exaone/system_prompt.py — 5-block 프롬프트 조합.

prompts/ 폴더의 텍스트 파일을 읽어 system blocks dict를 반환한다.
파일이 없으면 빈 문자열로 처리 (strict=False 시 오류 없이 스킵).

폴더 구조:
  exaone/prompts/
    identities/<name>.txt
    style/<name>.txt
    tools/<tool_name>.txt
"""

from datetime import datetime, timezone, timedelta
from pathlib import Path

_KST = timezone(timedelta(hours=9))

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_TOOLS_PROMPTS_DIR = _PROMPTS_DIR / "tools"
_SEP = "\n\n"


def compose_system_prompt(blocks: dict[str, str | None]) -> str:
    """Concat present blocks with double newline. Skip None / empty."""
    order = ["identity", "tool_list", "style", "custom", "memory"]
    parts = []
    for key in order:
        value = blocks.get(key)
        if value and value.strip():
            parts.append(value.strip())
    return _SEP.join(parts)


def load_prompt_blocks(
    identity_name: str = "default",
    style_name: str = "default",
    *,
    strict: bool = False,
) -> dict[str, str]:
    """identity/style 파일을 읽어 system blocks dict 반환.

    blocks keys: identity, style, tool_list, custom, memory
    strict=True이면 파일 누락 시 RuntimeError.
    """
    identity = _read_file(_PROMPTS_DIR / "identities" / f"{identity_name}.txt", "identity" if strict else None)
    style = _read_file(_PROMPTS_DIR / "style" / f"{style_name}.txt", "style" if strict else None)
    return {
        "identity": identity.strip(),
        "style": style.strip(),
        "tool_list": "",
        "custom": "",
        "memory": "",
    }


def compose_tool_list_for_tools(tool_names: "list[str] | tuple[str, ...]", *, strict: bool = True) -> str:
    """Compose tool_list prompt by concatenating per-tool descriptions.

    Reads descriptions from ``prompts/tools/<tool_name>.txt`` in the provided
    order (deduplicated, stable). Prepends ``prompts/tools/base_prompt.txt``
    when present. Raises RuntimeError on missing descriptions when strict=True.
    """
    base_prompt_path = _TOOLS_PROMPTS_DIR / "base_prompt.txt"
    sections = []
    if base_prompt_path.exists():
        base_text = base_prompt_path.read_text(encoding="utf-8").strip()
        if base_text:
            sections.append(base_text)
    elif strict:
        raise RuntimeError(
            f"Missing default tool base prompt file: {base_prompt_path}"
        )

    seen = set()
    descriptions = []
    for tool_name in tool_names:
        if tool_name in seen:
            continue
        seen.add(tool_name)
        path = _TOOLS_PROMPTS_DIR / f"{tool_name}.txt"
        if not path.exists():
            if strict:
                raise RuntimeError(
                    f"Missing tool description prompt for '{tool_name}': {path}"
                )
            continue
        descriptions.append(path.read_text(encoding="utf-8").strip())
    sections.extend(d for d in descriptions if d)
    return _SEP.join(sections)


def _read_file(path: Path, block_name: str | None = None) -> str:
    if not path.exists():
        if block_name is not None:
            raise RuntimeError(f"Missing {block_name} prompt file: {path}")
        return ""
    text = path.read_text(encoding="utf-8")
    return text.replace("{current_date}", datetime.now(_KST).strftime("%Y-%m-%d"))


def _join(*parts: str) -> str:
    return _SEP.join(p for p in parts if p and p.strip())
