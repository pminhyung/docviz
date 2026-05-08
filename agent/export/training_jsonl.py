"""
Training JSONL Exporter

Exports training data in backward-compatible JSONL format with new fields.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, TextIO

from ..core.trace_collector import TraceSession, SYSTEM_PROMPT_REDACTED


@dataclass
class TrainingSample:
    """
    A training sample in the backward-compatible format.

    Original fields (CRITICAL - must preserve):
    - df_idx: int
    - user_query: str
    - filenames: list[str]
    - reasoning: list[list[dict]]     # Each dict: role, content, loss_masking
    - readfulldocument: list[list[dict]]
    - readfulltext: list[list[dict]]
    - doc_step: list[dict]

    New fields (additive only):
    - version: str
    - train_system_prompt: str        # TRAINING_SYSTEM_PROMPT
    - runtime_prompt_hash: str        # SHA256
    - override_hash: str              # SHA256 of patch if any
    - session_id: str
    - language: str
    - trace_summary: dict             # Redacted trace
    - timestamp: str
    - metadata: dict
    """
    # Original fields
    df_idx: int = 0
    user_query: str = ""
    filenames: List[str] = field(default_factory=list)
    reasoning: List[List[Dict[str, Any]]] = field(default_factory=list)
    readfulldocument: List[List[Dict[str, Any]]] = field(default_factory=list)
    readfulltext: List[List[Dict[str, Any]]] = field(default_factory=list)
    doc_step: List[Dict[str, Any]] = field(default_factory=list)

    # Custom tool training data (커스텀 툴이 record_training으로 기록한 비표준 키)
    extra_training: Dict[str, List[List[Dict[str, Any]]]] = field(default_factory=dict)

    # New fields (v2)
    version: str = "2.0"
    train_system_prompt: str = ""
    runtime_prompt_hash: str = ""
    override_hash: Optional[str] = None
    session_id: str = ""
    language: str = "ENGLISH"
    trace_summary: Optional[Dict[str, Any]] = None
    timestamp: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        result = {
            # Original fields (order matters for compatibility)
            "df_idx": self.df_idx,
            "user_query": self.user_query,
            "filenames": self.filenames,
            "reasoning": self.reasoning,
            "readfulldocument": self.readfulldocument,
            "readfulltext": self.readfulltext,
            "doc_step": self.doc_step,
            # New fields
            "version": self.version,
            "train_system_prompt": self.train_system_prompt,
            "runtime_prompt_hash": self.runtime_prompt_hash,
            "session_id": self.session_id,
            "language": self.language,
            "timestamp": self.timestamp,
        }

        if self.override_hash:
            result["override_hash"] = self.override_hash

        if self.trace_summary:
            result["trace_summary"] = self.trace_summary

        if self.metadata:
            result["metadata"] = self.metadata

        # Expand custom training keys (e.g., "vl_analysis") into top-level
        if self.extra_training:
            result.update(self.extra_training)

        return result

    # Known keys for from_dict extra_training detection
    _KNOWN_KEYS = {
        "df_idx", "user_query", "filenames",
        "reasoning", "readfulldocument", "readfulltext", "doc_step",
        "extra_training",
    }
    _V2_KEYS = {
        "version", "train_system_prompt", "runtime_prompt_hash",
        "override_hash", "session_id", "language", "trace_summary",
        "timestamp", "metadata",
    }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TrainingSample":
        """Create from dictionary"""
        # Collect unknown list-valued keys as extra_training
        extra = {}
        all_known = cls._KNOWN_KEYS | cls._V2_KEYS
        for k, v in data.items():
            if k not in all_known and isinstance(v, list):
                extra[k] = v

        return cls(
            df_idx=data.get("df_idx", 0),
            user_query=data.get("user_query", ""),
            filenames=data.get("filenames", []),
            reasoning=data.get("reasoning", []),
            readfulldocument=data.get("readfulldocument", []),
            readfulltext=data.get("readfulltext", []),
            doc_step=data.get("doc_step", []),
            extra_training=extra,
            version=data.get("version", "1.0"),
            train_system_prompt=data.get("train_system_prompt", ""),
            runtime_prompt_hash=data.get("runtime_prompt_hash", ""),
            override_hash=data.get("override_hash"),
            session_id=data.get("session_id", ""),
            language=data.get("language", "ENGLISH"),
            trace_summary=data.get("trace_summary"),
            timestamp=data.get("timestamp", ""),
            metadata=data.get("metadata", {}),
        )


class TrainingJSONLExporter:
    """
    Exports training samples to JSONL format.

    Usage:
        exporter = TrainingJSONLExporter("train_samples.jsonl")
        exporter.export_sample(sample)
        exporter.close()

    Or with context manager:
        with TrainingJSONLExporter("train_samples.jsonl") as exporter:
            exporter.export_sample(sample)
    """

    def __init__(
        self,
        output_path: str,
        append: bool = True,
        ensure_ascii: bool = False
    ):
        """
        Initialize the exporter.

        Args:
            output_path: Path to output JSONL file
            append: Whether to append to existing file
            ensure_ascii: Whether to escape non-ASCII characters
        """
        self.output_path = Path(output_path)
        self.append = append
        self.ensure_ascii = ensure_ascii
        self._file: Optional[TextIO] = None
        self._samples_written = 0

    def __enter__(self) -> "TrainingJSONLExporter":
        """Context manager entry"""
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()

    def open(self) -> None:
        """Open the output file"""
        if self._file is not None:
            return

        mode = "a" if self.append else "w"
        self._file = open(self.output_path, mode, encoding="utf-8")

    def close(self) -> None:
        """Close the output file"""
        if self._file is not None:
            self._file.close()
            self._file = None

    def export_sample(self, sample: TrainingSample) -> None:
        """
        Export a single training sample.

        Args:
            sample: The training sample to export
        """
        if self._file is None:
            self.open()

        json_str = json.dumps(
            sample.to_dict(),
            ensure_ascii=self.ensure_ascii
        )
        self._file.write(json_str + "\n")
        self._samples_written += 1

    def export_dict(self, data: Dict[str, Any]) -> None:
        """
        Export a dictionary directly.

        Args:
            data: Dictionary to export
        """
        if self._file is None:
            self.open()

        json_str = json.dumps(data, ensure_ascii=self.ensure_ascii)
        self._file.write(json_str + "\n")
        self._samples_written += 1

    @property
    def samples_written(self) -> int:
        """Get number of samples written"""
        return self._samples_written


CHATEXAONE_SYSTEM_PREFIX = """You are a helpful assistant, ChatEXAONE(챗엑사원), designed by LG AI Research(LG AI 연구원) and built for providing safe and ethical responses. You can respond in both English and Korean. Please answer the question in the language the user requests or prefers. If you don't have enough information, avoid making assumptions or hallucinations.
Reference the below basic information.
- ChatEXAONE(챗엑사원) is designed by LG AI Research(LG AI 연구원)
- Claude(클로드) is created by Anthropic(앤소로픽), not by LG AI Research(LG AI 연구원)
- ChatGPT(챗지피티) is created by OpenAI(오픈에이아이), not by LG AI Research(LG AI 연구원)
- Gemini(제미나이) is created by Google(구글), not by LG AI Research(LG AI 연구원)

---

"""


def convert_base_train_sample(
    base_train_sample: Dict[str, Any],
    train_system_prompt: str,
    runtime_prompt_hash: str,
    session: Optional[TraceSession] = None,
    language: str = "ENGLISH",
    override_hash: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> TrainingSample:
    """
    Convert a base module train_sample to v2 format.

    Args:
        base_train_sample: The original train_sample dict from base module
        train_system_prompt: The training system prompt
        runtime_prompt_hash: Hash of the runtime prompt
        session: Optional trace session for summary
        language: Language setting
        override_hash: Hash of any patch override
        metadata: Additional metadata

    Returns:
        TrainingSample in v2 format
    """
    # Transform reasoning system prompts for training
    reasoning = _transform_reasoning_prompts(
        base_train_sample.get("reasoning", []),
        train_system_prompt=train_system_prompt,
    )

    # doc_step: insert chatexaone system turn
    doc_step = _insert_chatexaone_system(base_train_sample.get("doc_step", []))

    # readfulldocument: insert chatexaone system turn for each entry
    readfulldocument = [
        _insert_chatexaone_system(entry)
        for entry in base_train_sample.get("readfulldocument", [])
    ]

    # readfulltext: insert chatexaone system turn for each entry
    readfulltext = [
        _insert_chatexaone_system(entry)
        for entry in base_train_sample.get("readfulltext", [])
    ]

    # Collect custom training keys (e.g., "vl_analysis" from record_training)
    _KNOWN_BASE_KEYS = {
        "df_idx", "user_query", "filenames",
        "reasoning", "readfulldocument", "readfulltext", "doc_step",
    }
    extra_training = {}
    for key, value in base_train_sample.items():
        if key not in _KNOWN_BASE_KEYS and isinstance(value, list) and value:
            extra_training[key] = [
                _insert_chatexaone_system(entry) if isinstance(entry, list) else entry
                for entry in value
            ]

    # Build trace summary if session provided
    trace_summary = None
    session_id = ""
    if session:
        session_id = session.session_id
        trace_summary = {
            "num_steps": len(session.steps),
            "total_tokens": session.total_tokens,
            "total_duration_seconds": session.total_duration_seconds,
            "success": session.success,
            "actions_used": [
                step.action for step in session.steps
                if step.action
            ],
        }

    return TrainingSample(
        df_idx=base_train_sample.get("df_idx", 0),
        user_query=base_train_sample.get("user_query", ""),
        filenames=base_train_sample.get("filenames", []),
        reasoning=reasoning,
        readfulldocument=readfulldocument,
        readfulltext=readfulltext,
        doc_step=doc_step,
        extra_training=extra_training,
        train_system_prompt=train_system_prompt,
        runtime_prompt_hash=runtime_prompt_hash,
        override_hash=override_hash,
        session_id=session_id,
        language=language,
        trace_summary=trace_summary,
        metadata=metadata or {},
    )


def _transform_reasoning_prompts(
    reasoning: List[List[Dict[str, Any]]],
    train_system_prompt: str,
) -> List[List[Dict[str, Any]]]:
    """Replace reasoning system content with chatexaone_sys + training_system_prompt.

    Runtime system prompt -> chatexaone_sys + training_system_prompt for training.
    """
    result = []
    for turn_list in reasoning:
        transformed = []
        for turn in turn_list:
            if turn.get("role") == "system":
                transformed.append({
                    "role": "system",
                    "content": CHATEXAONE_SYSTEM_PREFIX + train_system_prompt,
                    "loss_masking": turn.get("loss_masking", True),
                })
            else:
                transformed.append(turn.copy())
        result.append(transformed)
    return result


def _insert_chatexaone_system(
    conversations: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Insert chatexaone_sys system turn at the front of a conversation.

    - If conversations already has a system turn first, prepend chatexaone_sys to its content.
    - Otherwise, insert a new system turn with chatexaone_sys.
    """
    if not conversations:
        return conversations
    if conversations[0].get("role") == "system":
        result = [conversations[0].copy()]
        result[0]["content"] = CHATEXAONE_SYSTEM_PREFIX + result[0]["content"]
        return result + [t.copy() for t in conversations[1:]]
    return [{"role": "system", "content": CHATEXAONE_SYSTEM_PREFIX.rstrip()}] + \
           [t.copy() for t in conversations]


def convert_base_train_sample_v1(
    base_train_sample: Dict[str, Any],
    train_system_prompt: str,
) -> Dict[str, Any]:
    """
    Convert a base train_sample to v1 format (default).

    v1 contains the original 7 keys + train_system_prompt + custom tool keys.
    No v2 metadata (version, runtime_prompt_hash, session_id, etc.).

    CHATEXAONE prefix is applied to:
    - reasoning system turns (prefix + train_system_prompt)
    - doc_step, readfulldocument, readfulltext
    - custom tool keys

    Args:
        base_train_sample: The original train_sample dict from builder
        train_system_prompt: The training system prompt

    Returns:
        Dict in v1 format
    """
    # Transform reasoning system prompts for training
    reasoning = _transform_reasoning_prompts(
        base_train_sample.get("reasoning", []),
        train_system_prompt=train_system_prompt,
    )

    # doc_step: insert chatexaone system turn
    doc_step = _insert_chatexaone_system(base_train_sample.get("doc_step", []))

    # readfulldocument: insert chatexaone system turn for each entry
    readfulldocument = [
        _insert_chatexaone_system(entry)
        for entry in base_train_sample.get("readfulldocument", [])
    ]

    # readfulltext: insert chatexaone system turn for each entry
    readfulltext = [
        _insert_chatexaone_system(entry)
        for entry in base_train_sample.get("readfulltext", [])
    ]

    result = {
        "df_idx": base_train_sample.get("df_idx", 0),
        "user_query": base_train_sample.get("user_query", ""),
        "filenames": base_train_sample.get("filenames", []),
        "reasoning": reasoning,
        "readfulldocument": readfulldocument,
        "readfulltext": readfulltext,
        "doc_step": doc_step,
        "train_system_prompt": train_system_prompt,
    }

    # Collect custom tool keys (anything not in the known base keys)
    _KNOWN_BASE_KEYS = {
        "df_idx", "user_query", "filenames",
        "reasoning", "readfulldocument", "readfulltext", "doc_step",
    }
    for key, value in base_train_sample.items():
        if key not in _KNOWN_BASE_KEYS and isinstance(value, list) and value:
            result[key] = [
                _insert_chatexaone_system(entry) if isinstance(entry, list) else entry
                for entry in value
            ]

    return result


def export_training_sample(
    output_path: str,
    train_sample: Dict[str, Any],
    train_system_prompt: str,
    runtime_prompt_hash: str,
    session: Optional[TraceSession] = None,
    language: str = "ENGLISH",
    override_hash: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    append: bool = True,
) -> None:
    """
    Convenience function to export a single training sample.

    Args:
        output_path: Path to output JSONL file
        train_sample: The base train_sample dict
        train_system_prompt: The training system prompt
        runtime_prompt_hash: Hash of the runtime prompt
        session: Optional trace session
        language: Language setting
        override_hash: Hash of any patch override
        metadata: Additional metadata
        append: Whether to append to existing file
    """
    sample = convert_base_train_sample(
        train_sample,
        train_system_prompt=train_system_prompt,
        runtime_prompt_hash=runtime_prompt_hash,
        session=session,
        language=language,
        override_hash=override_hash,
        metadata=metadata,
    )

    with TrainingJSONLExporter(output_path, append=append) as exporter:
        exporter.export_sample(sample)


def validate_training_sample(sample: Dict[str, Any]) -> List[str]:
    """
    Validate a training sample has required fields.

    Args:
        sample: The training sample dict

    Returns:
        List of validation errors (empty if valid)
    """
    errors = []

    # Required original fields
    required_fields = [
        "df_idx",
        "user_query",
        "filenames",
        "reasoning",
        "readfulldocument",
        "readfulltext",
        "doc_step",
    ]

    for field in required_fields:
        if field not in sample:
            errors.append(f"Missing required field: {field}")

    # Type checks
    if "filenames" in sample and not isinstance(sample["filenames"], list):
        errors.append("'filenames' must be a list")

    if "reasoning" in sample and not isinstance(sample["reasoning"], list):
        errors.append("'reasoning' must be a list")

    return errors
