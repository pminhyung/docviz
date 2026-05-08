"""
Event-based training sample builder.

Consolidates scattered train_sample mutations from:
- run_agent_v2.py  L401-409  (init)
- run_agent_v2.py  L470-473  (doc_step)
- run_agent_v2.py  L528-540  (reasoning turn)
- builtin_tools.py L229-233  (readfulldocument)
- builtin_tools.py L364-370  (readfulltext)
"""

import copy
from typing import Any, Dict, List

from ..reasoning.events import (
    DocSummaryCompleted,
    StepCompleted,
    ToolExtractionCompleted,
)


class TrainingSampleBuilder:
    """
    Builds a training sample dict incrementally via domain events.

    The ``build()`` output is compatible with ``convert_base_train_sample()``.
    """

    def __init__(
        self,
        user_query: str,
        filenames: List[str],
        df_idx: int = 0,
    ):
        # Matches run_agent_v2.py L401-409
        self._sample: Dict[str, Any] = {
            "df_idx": df_idx,
            "user_query": user_query,
            "filenames": list(filenames),
            "reasoning": [],
            "readfulldocument": [],
            "readfulltext": [],
            "doc_step": [],
        }

    def record_doc_step(self, event: DocSummaryCompleted) -> None:
        """
        Record document summary step.

        Replicates run_agent_v2.py L470-473::

            train_sample["doc_step"] = [
                {"role": "user", "content": doc_summ_prompt, "loss_masking": True},
                {"role": "assistant", "content": doc_summary, "loss_masking": False},
            ]
        """
        self._sample["doc_step"] = [
            {"role": "user", "content": event.prompt, "loss_masking": True},
            {"role": "assistant", "content": event.summary, "loss_masking": False},
        ]

    def record_reasoning_turn(self, event: StepCompleted) -> None:
        """
        Record a single reasoning turn (LLM call + response).

        Replicates run_agent_v2.py L528-540::

            action_state_for_train = []
            for turn in action_state:
                turn_copy = turn.copy()
                turn_copy["loss_masking"] = True
                action_state_for_train.append(turn_copy)

            train_sample["reasoning"].append(
                action_state_for_train + [
                    {"role": "assistant", "content": full_response, "loss_masking": False},
                ]
            )
        """
        action_state_for_train = []
        for turn in event.action_state:
            turn_copy = turn.copy()
            turn_copy["loss_masking"] = True
            action_state_for_train.append(turn_copy)

        self._sample["reasoning"].append(
            action_state_for_train + [
                {"role": "assistant", "content": event.response, "loss_masking": False},
            ]
        )

    def record_extraction(self, event: ToolExtractionCompleted) -> None:
        """
        Record a tool extraction (builtin or custom).

        Builtin tools (readfulldocument, readfulltext) use lowercased key.
        Custom tools use their original tool_name as key.
        """
        tool_key = event.tool_name.lower()

        if tool_key not in self._sample:
            self._sample[tool_key] = []

        entry = []
        for msg in event.messages:
            entry.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", ""),
                "loss_masking": True,
            })
        entry.append({
            "role": "assistant",
            "content": event.result,
            "loss_masking": False,
        })

        self._sample[tool_key].append(entry)

    def build(self) -> Dict[str, Any]:
        """
        Return a deep copy of the accumulated training sample.

        The output dict is directly compatible with
        ``convert_base_train_sample()`` from ``export/training_jsonl.py``.
        """
        return copy.deepcopy(self._sample)
