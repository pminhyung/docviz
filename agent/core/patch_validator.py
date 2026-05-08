"""
Patch Validator

Validates YAML patches before applying them to prompt blocks.
Ensures security and correctness of user-provided patches.
"""

import json
import re
from typing import Dict, Any, List, Set

from ..config.runtime_prompts import PromptBlock, PatchMode


class PatchValidationError(Exception):
    """Raised when a patch fails validation"""

    def __init__(self, message: str, errors: List[str] = None):
        super().__init__(message)
        self.errors = errors or [message]


class PatchValidator:
    """
    Validates YAML patches for prompt blocks.

    Validation rules:
    - Only allowed block IDs can be patched
    - TOOLS_* blocks: append only (no replace)
    - Appended tool JSON must parse and not duplicate names
    - Sealed blocks cannot be patched
    - Clear error messages on validation failure
    """

    # Block IDs that are allowed to be patched (static names)
    PATCHABLE_BLOCKS = {
        "RULES_BLOCK",
    }

    # Prefixes for dynamically generated patchable/append-only blocks
    PATCHABLE_PREFIXES = {"TOOLS_"}
    APPEND_ONLY_PREFIXES = {"TOOLS_"}

    # Required metadata fields
    REQUIRED_META_FIELDS = {"owner", "version"}

    def __init__(self):
        self._existing_tool_names: Set[str] = set()

    def validate(
        self,
        patch_data: Dict[str, Any],
        blocks: Dict[str, PromptBlock]
    ) -> None:
        """
        Validate a patch against the current blocks.

        Args:
            patch_data: The parsed YAML patch data
            blocks: Current prompt blocks

        Raises:
            PatchValidationError: If validation fails
        """
        errors = []

        # Validate structure
        if not isinstance(patch_data, dict):
            raise PatchValidationError("Patch must be a YAML dictionary")

        # Validate metadata
        meta_errors = self._validate_meta(patch_data.get("meta", {}))
        errors.extend(meta_errors)

        # Validate patches
        patches = patch_data.get("patches", {})
        if not isinstance(patches, dict):
            errors.append("'patches' must be a dictionary")
        else:
            # Extract existing tool names from blocks
            self._extract_existing_tool_names(blocks)

            for block_id, patch_spec in patches.items():
                block_errors = self._validate_block_patch(
                    block_id, patch_spec, blocks
                )
                errors.extend(block_errors)

        if errors:
            raise PatchValidationError(
                f"Patch validation failed with {len(errors)} error(s)",
                errors=errors
            )

    def _validate_meta(self, meta: Any) -> List[str]:
        """Validate patch metadata"""
        errors = []

        if not isinstance(meta, dict):
            return ["'meta' must be a dictionary"]

        missing = self.REQUIRED_META_FIELDS - set(meta.keys())
        if missing:
            errors.append(f"Missing required meta fields: {missing}")

        # Validate owner format (alphanumeric + underscore)
        owner = meta.get("owner", "")
        if owner and not re.match(r"^[a-zA-Z0-9_]+$", str(owner)):
            errors.append("'owner' must be alphanumeric with underscores only")

        # Validate version format
        version = meta.get("version", "")
        if version and not re.match(r"^[a-zA-Z0-9_.\-]+$", str(version)):
            errors.append("'version' must be alphanumeric with underscores, dots, and hyphens only")

        return errors

    def _validate_block_patch(
        self,
        block_id: str,
        patch_spec: Any,
        blocks: Dict[str, PromptBlock]
    ) -> List[str]:
        """Validate a single block patch"""
        errors = []

        # Check if block exists
        if block_id not in blocks:
            errors.append(f"Unknown block ID: {block_id}")
            return errors

        block = blocks[block_id]

        # Check if block is sealed
        if block.is_sealed:
            errors.append(f"Block '{block_id}' is sealed and cannot be patched")
            return errors

        # Check if block is patchable (static set or prefix match)
        is_patchable = block_id in self.PATCHABLE_BLOCKS or any(
            block_id.startswith(prefix) for prefix in self.PATCHABLE_PREFIXES
        )
        if not is_patchable:
            errors.append(f"Block '{block_id}' is not in the allowed patchable blocks")
            return errors

        # Validate patch spec structure
        if not isinstance(patch_spec, dict):
            errors.append(f"Patch for '{block_id}' must be a dictionary")
            return errors

        action = patch_spec.get("action", "append")
        content = patch_spec.get("content", "")

        # Validate action
        valid_actions = {"append", "replace", "prepend"}
        if action not in valid_actions:
            errors.append(
                f"Invalid action '{action}' for '{block_id}'. "
                f"Must be one of: {valid_actions}"
            )

        # Check append-only blocks (prefix-based)
        is_append_only = any(
            block_id.startswith(prefix) for prefix in self.APPEND_ONLY_PREFIXES
        )
        if is_append_only and action == "replace":
            errors.append(
                f"Block '{block_id}' only allows 'append' action, not 'replace'"
            )

        # Validate content
        if not isinstance(content, str):
            errors.append(f"Content for '{block_id}' must be a string")
            return errors

        # Validate tool JSON for TOOLS_* blocks
        if block_id.startswith("TOOLS_") and content.strip():
            tool_errors = self._validate_tool_json(block_id, content)
            errors.extend(tool_errors)

        return errors

    def _extract_existing_tool_names(self, blocks: Dict[str, PromptBlock]) -> None:
        """Extract existing tool names from TOOLS_* blocks"""
        self._existing_tool_names = set()

        for block_id, block in blocks.items():
            if block_id.startswith("TOOLS_"):
                # Try to extract tool name from JSON
                try:
                    # The content might have a leading comma, so clean it
                    content = block.content.strip()
                    if content.startswith(","):
                        content = content[1:]

                    tool_def = json.loads(content)
                    if isinstance(tool_def, dict) and "name" in tool_def:
                        self._existing_tool_names.add(tool_def["name"])
                except json.JSONDecodeError:
                    pass  # Not valid JSON, skip

    def _validate_tool_json(self, block_id: str, content: str) -> List[str]:
        """Validate tool JSON content"""
        errors = []

        # Content might have leading comma for appending
        content = content.strip()
        if content.startswith(","):
            content = content[1:].strip()

        if not content:
            return errors  # Empty content is OK

        try:
            tool_def = json.loads(content)
        except json.JSONDecodeError as e:
            errors.append(
                f"Invalid JSON in '{block_id}' patch: {e}"
            )
            return errors

        # Validate tool structure
        if not isinstance(tool_def, dict):
            errors.append(
                f"Tool definition in '{block_id}' must be a JSON object"
            )
            return errors

        # Check required fields
        if "name" not in tool_def:
            errors.append(
                f"Tool definition in '{block_id}' must have a 'name' field"
            )

        if "description" not in tool_def:
            errors.append(
                f"Tool definition in '{block_id}' should have a 'description' field"
            )

        if "parameters" not in tool_def:
            errors.append(
                f"Tool definition in '{block_id}' should have a 'parameters' field"
            )

        # Check for duplicate tool name
        tool_name = tool_def.get("name", "")
        if tool_name and tool_name in self._existing_tool_names:
            errors.append(
                f"Duplicate tool name '{tool_name}' in '{block_id}' patch. "
                f"Tool already exists."
            )

        return errors

    def validate_content_security(self, content: str) -> List[str]:
        """
        Validate content for potential security issues.

        Args:
            content: The patch content to validate

        Returns:
            List of security-related warnings/errors
        """
        warnings = []

        # Check for potential injection patterns
        dangerous_patterns = [
            (r"<script", "Potential script injection"),
            (r"javascript:", "Potential JavaScript injection"),
            (r"\$\{.*\}", "Potential template injection"),
            (r"{{.*}}", "Potential template injection"),
            (r"__import__", "Potential Python import injection"),
            (r"eval\s*\(", "Potential eval injection"),
            (r"exec\s*\(", "Potential exec injection"),
        ]

        for pattern, message in dangerous_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                warnings.append(f"Security warning: {message} detected in content")

        return warnings
