"""
Output Validator for Document Agent V2

Validates agent responses and traces for format compliance,
policy adherence, and language consistency.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ValidationResult:
    """Result of validation check"""
    ok: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)


class OutputValidator:
    """
    Validates agent output for format, policy, and language compliance.

    Validation Rules:
    - Format: Has <tool_invoke> OR <final_answer>
    - Format: <tool_invoke> JSON parses with name + arguments
    - Format: No tool names in reasoning/observation/step_name (warning)
    - Policy: At least one doc action before final_answer (if docs exist)
    - Language (EN): Hangul ratio < 10% in final_answer
    - Language (KO): Hangul ratio > 20%, has polite endings
    """

    # Known tool names that should not appear in reasoning text
    TOOL_NAMES = ["search", "ReadFullDocument", "GetPage", "ReadFullText"]

    # Hangul Unicode range
    HANGUL_PATTERN = re.compile(r'[\uAC00-\uD7AF\u1100-\u11FF\u3130-\u318F]')

    # Korean polite endings
    KOREAN_POLITE_ENDINGS = ['습니다', '니다', '세요', '요', '습니까', '니까']

    # Citation pattern [N] where N is a number
    CITATION_PATTERN = re.compile(r'\[(\d+)\]')

    def __init__(self, language: str = "ENGLISH", has_documents: bool = True):
        """
        Initialize validator.

        Args:
            language: Expected language ("ENGLISH" or "KOREAN")
            has_documents: Whether documents were provided (affects doc action policy)
        """
        self.language = language.upper()
        self.has_documents = has_documents

    def validate_response(
        self,
        response: str,
        step_history: Optional[List[Dict[str, Any]]] = None
    ) -> ValidationResult:
        """
        Validate a single agent response.

        Args:
            response: Raw LLM response text
            step_history: Previous steps for context (optional)

        Returns:
            ValidationResult with ok status, errors, warnings, and stats
        """
        errors: List[str] = []
        warnings: List[str] = []
        stats: Dict[str, Any] = {
            "steps_count": len(step_history) if step_history else 0,
            "tool_invoke_count": 0,
            "citation_count": 0,
        }

        # Check for required tags
        has_tool_invoke = "<tool_invoke>" in response and "</tool_invoke>" in response
        has_final_answer = "<final_answer>" in response and "</final_answer>" in response

        if not has_tool_invoke and not has_final_answer:
            errors.append("Response must contain <tool_invoke> OR <final_answer>")

        # Validate tool_invoke format
        if has_tool_invoke:
            tool_invoke_errors, tool_count = self._validate_tool_invoke(response)
            errors.extend(tool_invoke_errors)
            stats["tool_invoke_count"] = tool_count

        # Check for tool names in reasoning/observation (warning)
        reasoning_warnings = self._check_tool_names_in_text(response)
        warnings.extend(reasoning_warnings)

        # Validate final_answer
        if has_final_answer:
            final_answer = self._extract_tag_content(response, "final_answer")
            if final_answer:
                # Count citations
                stats["citation_count"] = len(self.CITATION_PATTERN.findall(final_answer))

                # Language validation
                lang_warnings = self._validate_language(final_answer)
                warnings.extend(lang_warnings)

        # Policy: Check for doc action before final_answer
        if has_final_answer and self.has_documents:
            policy_warnings = self._check_doc_action_policy(response, step_history)
            warnings.extend(policy_warnings)

        ok = len(errors) == 0

        return ValidationResult(
            ok=ok,
            errors=errors,
            warnings=warnings,
            stats=stats
        )

    def validate_trace(
        self,
        trace: Dict[str, Any],
        constraints: Optional[Dict[str, Any]] = None
    ) -> ValidationResult:
        """
        Validate a complete trace/session.

        Args:
            trace: Trace dict with steps, user_query, etc.
            constraints: Optional validation constraints

        Returns:
            ValidationResult with ok status, errors, warnings, and stats
        """
        errors: List[str] = []
        warnings: List[str] = []

        steps = trace.get("steps", [])
        stats: Dict[str, Any] = {
            "steps_count": len(steps),
            "tool_invoke_count": 0,
            "citation_count": 0,
        }

        # Count tool invocations across all steps
        for step in steps:
            if step.get("action"):
                stats["tool_invoke_count"] += 1

        # Get final answer from last step
        final_answer = None
        for step in reversed(steps):
            if step.get("final_answer"):
                final_answer = step["final_answer"]
                break

        if final_answer:
            stats["citation_count"] = len(self.CITATION_PATTERN.findall(final_answer))

            # Language validation
            lang_warnings = self._validate_language(final_answer)
            warnings.extend(lang_warnings)

        # Check if trace completed successfully
        if not trace.get("success", False) and not final_answer:
            errors.append("Trace did not complete successfully and has no final_answer")

        # Policy: Check for document action in trace
        if self.has_documents:
            has_doc_action = False
            for step in steps:
                action = step.get("action")
                if action:
                    # action can be a string or a dict
                    if isinstance(action, dict):
                        action_name = action.get("name", "")
                    else:
                        action_name = str(action)
                    if action_name in ["ReadFullDocument", "GetPage", "ReadFullText", "search", "doc_summary"]:
                        has_doc_action = True
                        break
            if not has_doc_action and final_answer:
                warnings.append("No document action found before final_answer")

        # Apply constraints if provided
        if constraints:
            constraint_errors, constraint_warnings = self._apply_constraints(trace, constraints)
            errors.extend(constraint_errors)
            warnings.extend(constraint_warnings)

        ok = len(errors) == 0

        return ValidationResult(
            ok=ok,
            errors=errors,
            warnings=warnings,
            stats=stats
        )

    def _validate_tool_invoke(self, response: str) -> tuple:
        """
        Validate tool_invoke tag content.

        Returns:
            Tuple of (errors list, tool count)
        """
        errors = []
        tool_count = 0

        # Find all tool_invoke blocks
        pattern = re.compile(r'<tool_invoke>(.*?)</tool_invoke>', re.DOTALL)
        matches = pattern.findall(response)

        for match in matches:
            try:
                tool_json = json.loads(match.strip())
                tool_count += 1

                if "name" not in tool_json:
                    errors.append("tool_invoke JSON missing 'name' field")
                if "arguments" not in tool_json:
                    errors.append("tool_invoke JSON missing 'arguments' field")

            except json.JSONDecodeError as e:
                errors.append(f"tool_invoke JSON parse error: {str(e)}")

        return errors, tool_count

    def _check_tool_names_in_text(self, response: str) -> List[str]:
        """
        Check if tool names appear inappropriately in reasoning/observation text.

        Returns:
            List of warnings
        """
        warnings = []

        # Extract reasoning and observation content
        reasoning = self._extract_tag_content(response, "reasoning")
        observation = self._extract_tag_content(response, "observation")
        step_name = self._extract_tag_content(response, "step_name")

        combined_text = " ".join(filter(None, [reasoning, observation, step_name]))

        # Check for tool names that look like they're being mentioned as actions
        # Skip if the text is describing what will be done
        for tool_name in self.TOOL_NAMES:
            # Pattern to catch tool names being used as raw actions (not in context)
            if re.search(rf'\b{tool_name}\s*\(', combined_text):
                warnings.append(
                    f"Tool name '{tool_name}' appears as function call in reasoning/observation"
                )

        return warnings

    def _validate_language(self, text: str) -> List[str]:
        """
        Validate language consistency.

        Returns:
            List of warnings
        """
        warnings = []

        if not text:
            return warnings

        # Calculate Hangul ratio
        hangul_chars = len(self.HANGUL_PATTERN.findall(text))
        total_chars = len(text.replace(" ", "").replace("\n", ""))

        if total_chars == 0:
            return warnings

        hangul_ratio = hangul_chars / total_chars

        if self.language == "ENGLISH":
            if hangul_ratio >= 0.10:
                warnings.append(
                    f"English response has {hangul_ratio:.1%} Hangul characters (expected < 10%)"
                )
        elif self.language == "KOREAN":
            if hangul_ratio < 0.20:
                warnings.append(
                    f"Korean response has only {hangul_ratio:.1%} Hangul characters (expected > 20%)"
                )
            else:
                # Check for polite endings
                has_polite_ending = any(
                    text.rstrip().endswith(ending) or ending in text
                    for ending in self.KOREAN_POLITE_ENDINGS
                )
                if not has_polite_ending:
                    warnings.append("Korean response may lack polite speech endings")

        return warnings

    def _check_doc_action_policy(
        self,
        response: str,
        step_history: Optional[List[Dict[str, Any]]]
    ) -> List[str]:
        """
        Check if document action was performed before final_answer.

        Returns:
            List of warnings
        """
        warnings = []

        # Check step history for doc actions
        if step_history:
            has_doc_action = any(
                step.get("action", {}).get("name") in self.TOOL_NAMES
                for step in step_history
                if step.get("action")
            )
            if not has_doc_action:
                warnings.append("No document action found before final_answer")
        else:
            # If no history, we can't verify - just note it
            warnings.append("Cannot verify document action policy (no step history)")

        return warnings

    def _extract_tag_content(self, text: str, tag: str) -> Optional[str]:
        """
        Extract content from XML-like tag.

        Args:
            text: Source text
            tag: Tag name

        Returns:
            Tag content or None
        """
        pattern = re.compile(rf'<{tag}>(.*?)</{tag}>', re.DOTALL)
        match = pattern.search(text)
        return match.group(1).strip() if match else None

    def _apply_constraints(
        self,
        trace: Dict[str, Any],
        constraints: Dict[str, Any]
    ) -> tuple:
        """
        Apply custom constraints to trace.

        Returns:
            Tuple of (errors, warnings)
        """
        errors = []
        warnings = []

        # Max steps constraint
        if "max_steps" in constraints:
            steps_count = len(trace.get("steps", []))
            if steps_count > constraints["max_steps"]:
                warnings.append(
                    f"Trace has {steps_count} steps, exceeds max_steps constraint of {constraints['max_steps']}"
                )

        # Required tools constraint
        if "required_tools" in constraints:
            used_tools = set()
            for step in trace.get("steps", []):
                if step.get("action"):
                    used_tools.add(step["action"].get("name"))

            missing_tools = set(constraints["required_tools"]) - used_tools
            if missing_tools:
                warnings.append(f"Required tools not used: {missing_tools}")

        # Min citations constraint
        if "min_citations" in constraints:
            steps = trace.get("steps", [])
            final_answer = None
            for step in reversed(steps):
                if step.get("final_answer"):
                    final_answer = step["final_answer"]
                    break

            if final_answer:
                citation_count = len(self.CITATION_PATTERN.findall(final_answer))
                if citation_count < constraints["min_citations"]:
                    warnings.append(
                        f"Only {citation_count} citations found, expected at least {constraints['min_citations']}"
                    )

        return errors, warnings
