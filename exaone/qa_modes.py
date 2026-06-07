"""qa_mode definitions and validation for ExaoneAgent."""

import os
from dataclasses import dataclass
from pathlib import Path


# docviz B6 axis ablations. v0.4.1 §5.3 (CIS/TMG/SAO) + v0.4.3 §7 (SEF/VSC).
# Resolved at agent init. SEF/VSC are tool/input-level, not prompt-level, so
# they reuse the base "docviz" identity; the tool reads DOCVIZ_VARIANT to toggle
# behavior (novsc → direct-DSL, no repair) and the document layer routes input
# (nosef → plain markdown instead of SEF JSON).
DOCVIZ_VARIANT_ENV = "DOCVIZ_VARIANT"
DOCVIZ_VARIANTS = {
    "full":   "docviz",          # B6 full (CIS + SEF + TMG + SAO + VSC active)
    "nocis":  "docviz_nocis",    # − CIS pillar
    "nosao":  "docviz_nosao",    # − SAO pillar
    "notmg":  "docviz_notmg",    # − TMG pillar (no generate_viz exposure)
    "nosef":  "docviz",          # − SEF (B6 gets plain markdown; routed upstream)
    "novsc":  "docviz",          # − VSC (direct DSL, no contract/repair; tool toggle)
}


def _resolve_docviz_identity() -> str:
    """Return the identity filename stem for the currently-selected docviz variant."""
    variant = os.environ.get(DOCVIZ_VARIANT_ENV, "full").strip().lower()
    return DOCVIZ_VARIANTS.get(variant, "docviz")


@dataclass(frozen=True)
class QaModeConfig:
    name: str
    toolset: list[str]
    identity_name: str
    style_name: str


QA_MODES: dict[str, QaModeConfig] = {
    "general": QaModeConfig(
        name="general",
        # TODO: implement doc_tool, code_tool
        # toolset=["web_tools", "doc_tools", "code_tools"],
        toolset=["web_tools", "code_tools"],
        identity_name="default",
        style_name="default",
    ),
    "research": QaModeConfig(
        name="research",
        # TODO: implement doc_tool 
        # toolset=["web_tools", "doc_tools"],
        toolset=["web_tools"],
        identity_name="research",
        style_name="research",
    ),
    "canvas": QaModeConfig(
        name="canvas",
        # TODO: implement canvas_tool
        # toolset=["canvas_tools"],
        toolset=["web_tools"],
        identity_name="think",
        style_name="think",
    ),
    "docqa": QaModeConfig(
        name="docqa",
        toolset=[
            "web_tools",
            "parsing_tools",
            "docqa_tools",
            "pdf_tools",
            "pptx_tools",
            "docx_tools",
            "hwpx_tools",
            "xlsx_tools",
        ],
        identity_name="docqa",
        style_name="docqa",
    ),
    # Multimodal DOCQA — adds visual_tools (get_visuals / analyze_visual)
    # and the per-extension page-layout tools (pdf_page_layout +
    # pptx/docx/hwpx/xlsx stubs) on top of docqa's text toolset. Use this
    # mode when the deployer has a VLM endpoint wired up; pure-text docqa
    # remains a separate mode so deployments without a vision backend
    # can still serve text RAG.
    "mm_docqa": QaModeConfig(
        name="mm_docqa",
        toolset=[
            "web_tools",
            "parsing_tools",
            "docqa_tools",
            "visual_tools",
            "pdf_tools",
            "pptx_tools",
            "docx_tools",
            "hwpx_tools",
            "xlsx_tools",
        ],
        identity_name="mm_docqa",
        style_name="mm_docqa",
    ),
    # taskbot — same toolset as docqa minus web_tools. For deployments
    # that must operate strictly on attached documents (no public web
    # access). Uses dedicated identity/style prompts that drop every
    # mention of web_search / web_extract so the model is never told
    # to fall back to the web from this mode.
    "taskbot": QaModeConfig(
        name="taskbot",
        toolset=[
            "parsing_tools",
            "docqa_tools",
            "pdf_tools",
            "pptx_tools",
            "docx_tools",
            "hwpx_tools",
            "xlsx_tools",
        ],
        identity_name="taskbot",
        style_name="taskbot",
    ),
    # docviz — query-grounded multi-document visualization agent (v0.4.1 B6).
    # Identity file selected at agent init via DOCVIZ_VARIANT env (full /
    # nocis / nosao / notmg) for §5.3 pillar ablation. Same style across all
    # variants. Toolset = ir-shim docqa + viz_tools.
    "docviz": QaModeConfig(
        name="docviz",
        toolset=[
            "parsing_tools",
            "docqa_tools",
            "viz_tools",
        ],
        identity_name=_resolve_docviz_identity(),
        style_name="docviz",
    ),
}


def validate_exclusive_modes(toolset, qa_mode) -> None:
    """toolset and qa_mode cannot be used together."""
    if toolset is not None and qa_mode is not None:
        raise ValueError("toolset and qa_mode are mutually exclusive")


def resolve_qa_mode(qa_mode: str) -> QaModeConfig:
    """Resolve qa_mode into a concrete mode definition."""
    if not isinstance(qa_mode, str) or not qa_mode.strip():
        raise ValueError("qa_mode must be a non-empty string")
    key = qa_mode.strip()
    config = QA_MODES.get(key)
    if config is None:
        valid = ", ".join(sorted(QA_MODES.keys())) or "(none)"
        raise ValueError(f"Unknown qa_mode '{key}'. Available modes: {valid}")
    return config


def validate_qa_mode_prompt_files(qa_mode: str) -> QaModeConfig:
    """Validate that required prompt files exist for the requested qa_mode."""
    config = resolve_qa_mode(qa_mode)
    prompts_dir = Path(__file__).parent / "prompts"
    identity_path = prompts_dir / "identities" / f"{config.identity_name}.txt"
    style_path = prompts_dir / "style" / f"{config.style_name}.txt"
    missing = [str(p) for p in (identity_path, style_path) if not p.exists()]
    if missing:
        raise RuntimeError(
            f"qa_mode '{config.name}' is missing required prompt files: {', '.join(missing)}"
        )
    return config
