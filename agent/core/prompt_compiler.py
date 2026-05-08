"""
Prompt Compiler

Compiles prompts from blocks with optional YAML patch support.
Produces both runtime (sealed) and training (redacted) prompts.
Supports custom tool injection and custom rules injection.
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any

import yaml

from ..config.runtime_prompts import (
    get_runtime_prompt_blocks,
    assemble_runtime_prompt,
    PromptBlock,
    PatchMode,
    RuntimePrompts,
)
from ..config.training_prompts import get_training_system_prompt
from .patch_validator import PatchValidator, PatchValidationError


# Language-specific patches
KO_LANG_PATCH = """**모든 'observation', 'reasoning', 'step_name', 'final_answer'는 반드시 한국어로 작성되어야 합니다.**
**사용자 질문이 한국어인 경우 '~습니다', '~입니다' 형식의 정중한 어조를 사용하세요.**"""

EN_LANG_PATCH = """**All 'observation', 'reasoning', 'step_name', and 'final_answer' text MUST BE written in English.**
**Use professional and formal tone in all responses.**"""

# Final answer format patch
FINAL_ANSWER_PATCH = """When providing the final answer:
1. Structure your response with clear sections and headers when appropriate.
2. Include citations [N] for all factual claims derived from documents.
3. Be comprehensive yet concise - prioritize the most relevant information.
4. Use the appropriate language as specified in the instructions."""

# ChatExaone training prepend patch
CHATEXAONE_PATCH = """[|system|]You are EXAONE model from LG AI Research, a helpful assistant."""


@dataclass
class CompiledPrompt:
    """Result of prompt compilation"""
    runtime_prompt: str         # Full prompt for LLM (sealed)
    training_prompt: str        # Redacted prompt for export
    prompt_pack_id: str         # e.g., "baseline_v1"
    prompt_hash: str            # SHA256 of runtime prompt
    override_hash: Optional[str] = None  # SHA256 of patch if any
    patch_metadata: Optional[Dict[str, Any]] = None  # Patch metadata if applied

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "prompt_pack_id": self.prompt_pack_id,
            "prompt_hash": self.prompt_hash,
            "override_hash": self.override_hash,
            "patch_metadata": self.patch_metadata,
        }


class PromptCompiler:
    """
    Compiles prompts from blocks with optional YAML patches.

    Usage:
        compiler = PromptCompiler(language="ENGLISH")
        compiled = compiler.compile(patch_file="override.yaml")
        # compiled.runtime_prompt - full prompt for LLM
        # compiled.training_prompt - redacted for training export
    """

    BASELINE_PACK_ID = "baseline_v1"

    def __init__(
        self,
        language: str = "ENGLISH",
        cur_date: Optional[str] = None
    ):
        """
        Initialize the compiler.

        Args:
            language: The language for the agent output ("ENGLISH" or "KOREAN")
            cur_date: Current date string. If None, uses today's date.
        """
        self.language = language
        self.cur_date = cur_date
        self.validator = PatchValidator()
        self._blocks: Optional[Dict[str, PromptBlock]] = None
        self._patches: Optional[Dict[str, Any]] = None
        self._patch_metadata: Optional[Dict[str, Any]] = None

    def _load_blocks(self) -> Dict[str, PromptBlock]:
        """Load the base prompt blocks"""
        if self._blocks is None:
            self._blocks = get_runtime_prompt_blocks(
                language=self.language,
                cur_date=self.cur_date
            )
        return self._blocks

    def load_patch(self, patch_file: str) -> Dict[str, Any]:
        """
        Load and validate a YAML patch file.

        Args:
            patch_file: Path to the YAML patch file

        Returns:
            Parsed patch dictionary

        Raises:
            FileNotFoundError: If patch file doesn't exist
            PatchValidationError: If patch is invalid
        """
        patch_path = Path(patch_file)
        if not patch_path.exists():
            raise FileNotFoundError(f"Patch file not found: {patch_file}")

        with open(patch_path, "r", encoding="utf-8") as f:
            patch_data = yaml.safe_load(f)

        # Validate the patch
        blocks = self._load_blocks()
        self.validator.validate(patch_data, blocks)

        self._patches = patch_data.get("patches", {})
        self._patch_metadata = patch_data.get("meta", {})

        return patch_data

    def apply_patches(self, patches: Dict[str, Any]) -> None:
        """
        Apply patches to the loaded blocks.

        Args:
            patches: Dictionary of block_id -> patch specification
        """
        blocks = self._load_blocks()

        for block_id, patch_spec in patches.items():
            if block_id not in blocks:
                continue  # Skip unknown blocks (already validated)

            block = blocks[block_id]
            action = patch_spec.get("action", "append")
            content = patch_spec.get("content", "")

            if action == "append":
                block.content = block.content + content
            elif action == "replace":
                block.content = content
            # "prepend" could be added if needed

    def compile(
        self,
        patch_file: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        custom_tools: Optional[List[Dict[str, Any]]] = None,
        custom_rules: Optional[str] = None,
        lang: str = "en"
    ) -> CompiledPrompt:
        """
        Compile the full prompt from blocks with optional patch.

        Args:
            patch_file: Optional path to YAML patch file
            tools: All tool definitions (builtin + custom) from ToolRegistry.
                   [{name, description, parameters}, ...]
                   When provided, generates per-tool TOOLS_* blocks dynamically.
            custom_tools: Deprecated. Use tools instead. If both are provided,
                         tools takes precedence.
            custom_rules: Optional custom rules to inject
                         Format: "- rule1\n- rule2..."
            lang: Language code ('ko' or 'en')

        Returns:
            CompiledPrompt with runtime and training prompts
        """
        # Load base blocks (creates fresh copy)
        self._blocks = None  # Force reload
        blocks = self._load_blocks()

        # Apply YAML patches if provided
        override_hash = None
        if patch_file:
            patch_data = self.load_patch(patch_file)
            self.apply_patches(self._patches)

            # Calculate override hash
            patch_json = json.dumps(patch_data, sort_keys=True)
            override_hash = hashlib.sha256(patch_json.encode()).hexdigest()[:16]

        # Inject custom rules into RULES_BLOCK
        if custom_rules:
            rules_block = blocks.get("RULES_BLOCK")
            if rules_block:
                rules_block.content = self._inject_custom_rules(
                    rules_block.content,
                    custom_rules
                )

        # Generate per-tool blocks dynamically
        all_tools = tools or custom_tools
        if all_tools:
            for i, tool in enumerate(all_tools):
                tool_json = json.dumps({
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["parameters"]
                }, ensure_ascii=False)
                block_id = f"TOOLS_{tool['name'].upper()}"
                blocks[block_id] = PromptBlock(
                    block_id=block_id,
                    content=tool_json,
                    order=RuntimePrompts.ORDER_TOOLS_SEARCH + (i * 5),
                    is_sealed=False,
                    patch_mode=PatchMode.APPEND,
                )

        # Assemble base runtime prompt
        base_prompt = assemble_runtime_prompt(blocks, include_tools=True)

        # Add language patch for runtime
        lang_patch = self._get_lang_patch(lang)
        runtime_prompt = (
            base_prompt +
            "\n\n" +
            FINAL_ANSWER_PATCH +
            "\n\n" +
            lang_patch
        )

        # Build training prompt (shortened version for SFT efficiency)
        # Uses the condensed TRAINING_SYSTEM_PROMPT instead of full base_prompt
        training_prompt = get_training_system_prompt(
            language=self.language,
            cur_date=self.cur_date
        )

        # Calculate runtime prompt hash
        prompt_hash = hashlib.sha256(runtime_prompt.encode()).hexdigest()[:16]

        # Determine pack ID
        pack_id = self.BASELINE_PACK_ID
        if self._patch_metadata:
            owner = self._patch_metadata.get("owner", "unknown")
            version = self._patch_metadata.get("version", "v1")
            pack_id = f"{owner}_{version}"

        return CompiledPrompt(
            runtime_prompt=runtime_prompt,
            training_prompt=training_prompt,
            prompt_pack_id=pack_id,
            prompt_hash=prompt_hash,
            override_hash=override_hash,
            patch_metadata=self._patch_metadata,
        )

    def _inject_custom_rules(self, rules_content: str, custom_rules: str) -> str:
        """
        Inject custom rules into RULES_BLOCK content.

        Custom rules are added after the last numbered rule,
        with automatic numbering starting from last_num + 1.

        Args:
            rules_content: Existing RULES_BLOCK content (rules 1-16)
            custom_rules: Custom rules to add
                         Format: "- rule1\n- rule2..." or "rule1\nrule2..."

        Returns:
            Extended RULES_BLOCK content
        """
        if not custom_rules or not custom_rules.strip():
            return rules_content

        # Find the current last rule number (default 16)
        numbers = re.findall(r'^(\d+)\.', rules_content, re.MULTILINE)
        last_num = max(int(n) for n in numbers) if numbers else 16

        # Parse and number custom rules
        custom_lines = []
        for line in custom_rules.strip().split('\n'):
            line = line.strip()
            if not line:
                continue

            if line.startswith('- '):
                # "- rule text" -> "17. rule text"
                last_num += 1
                custom_lines.append(f"{last_num}. {line[2:]}")
            elif re.match(r'^\d+\.', line):
                # Already numbered, renumber
                last_num += 1
                text = re.sub(r'^\d+\.\s*', '', line)
                custom_lines.append(f"{last_num}. {text}")
            else:
                # Plain text
                last_num += 1
                custom_lines.append(f"{last_num}. {line}")

        if custom_lines:
            return rules_content + "\n" + "\n".join(custom_lines)
        return rules_content

    def _get_lang_patch(self, lang: str) -> str:
        """
        Get language-specific patch.

        Args:
            lang: Language code ('ko' or 'en')

        Returns:
            Language patch string
        """
        lang_lower = lang.lower()
        if lang_lower in ("ko", "korean"):
            return KO_LANG_PATCH
        elif lang_lower in ("en", "english"):
            return EN_LANG_PATCH
        else:
            # Default to English
            return EN_LANG_PATCH

    def get_block_info(self) -> List[Dict[str, Any]]:
        """
        Get information about all prompt blocks.

        Returns:
            List of block information dictionaries
        """
        blocks = self._load_blocks()

        return [
            {
                "block_id": block.block_id,
                "order": block.order,
                "is_sealed": block.is_sealed,
                "patch_mode": block.patch_mode.value,
                "content_length": len(block.content),
            }
            for block in sorted(blocks.values(), key=lambda b: b.order)
        ]
