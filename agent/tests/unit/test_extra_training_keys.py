"""Unit tests for extra_training key preservation in TrainingSample.

Verifies that custom training keys (e.g., "vl_analysis") recorded via
context["record_training"] are preserved through the v2 conversion pipeline.
"""

import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from agent.export.training_jsonl import (
    TrainingSample,
    convert_base_train_sample,
)


class TestExtraTrainingPreservation:
    def test_custom_key_preserved(self):
        """Custom training key should survive convert_base_train_sample."""
        base = {
            "reasoning": [],
            "doc_step": [],
            "readfulldocument": [],
            "readfulltext": [],
            "vl_analysis": [[
                {"role": "user", "content": "Analyze this chart", "loss_masking": True},
                {"role": "assistant", "content": "Chart shows upward trend", "loss_masking": False},
            ]],
        }
        ts = convert_base_train_sample(base, "sys_prompt", "hash123")
        d = ts.to_dict()

        assert "vl_analysis" in d
        assert len(d["vl_analysis"]) == 1
        # _insert_chatexaone_system inserts a system turn at [0],
        # so user turn moves to [1]
        entry = d["vl_analysis"][0]
        assert entry[0]["role"] == "system"  # CHATEXAONE prefix inserted
        # Find user turn
        user_turns = [t for t in entry if t["role"] == "user"]
        assert len(user_turns) == 1
        assert user_turns[0]["content"] == "Analyze this chart"

    def test_custom_key_chatexaone_prefix(self):
        """Custom training entries should get CHATEXAONE system prefix applied."""
        base = {
            "reasoning": [],
            "doc_step": [],
            "readfulldocument": [],
            "readfulltext": [],
            "vl_analysis": [[
                {"role": "system", "content": "You are a helpful assistant"},
                {"role": "user", "content": "test", "loss_masking": True},
                {"role": "assistant", "content": "result", "loss_masking": False},
            ]],
        }
        ts = convert_base_train_sample(base, "sys_prompt", "hash123")
        d = ts.to_dict()

        assert "vl_analysis" in d
        # The system turn should have CHATEXAONE prefix prepended
        system_content = d["vl_analysis"][0][0]["content"]
        assert "You are a helpful assistant" in system_content

    def test_to_dict_includes_extra(self):
        """TrainingSample.to_dict() should include extra_training keys at top level."""
        ts = TrainingSample(
            extra_training={
                "vl_analysis": [[{"role": "user", "content": "test"}]],
                "custom_ocr": [[{"role": "user", "content": "ocr test"}]],
            }
        )
        d = ts.to_dict()

        assert "vl_analysis" in d
        assert "custom_ocr" in d
        assert d["vl_analysis"][0][0]["content"] == "test"

    def test_from_dict_restores_extra(self):
        """Round-trip: to_dict → from_dict should preserve extra_training."""
        ts_original = TrainingSample(
            user_query="test query",
            extra_training={
                "vl_analysis": [[
                    {"role": "user", "content": "prompt"},
                    {"role": "assistant", "content": "response"},
                ]],
            },
        )
        d = ts_original.to_dict()
        ts_restored = TrainingSample.from_dict(d)

        assert "vl_analysis" in ts_restored.extra_training
        assert len(ts_restored.extra_training["vl_analysis"]) == 1
        assert ts_restored.user_query == "test query"

    def test_empty_extra_training(self):
        """Empty extra_training should not add keys to dict."""
        ts = TrainingSample()
        d = ts.to_dict()

        # Standard keys should be present
        assert "reasoning" in d
        assert "readfulldocument" in d
        # No extra keys beyond the known set
        known = {
            "df_idx", "user_query", "filenames",
            "reasoning", "readfulldocument", "readfulltext", "doc_step",
            "version", "train_system_prompt", "runtime_prompt_hash",
            "session_id", "language", "timestamp",
        }
        for key in d:
            assert key in known or key in ("override_hash", "trace_summary", "metadata")

    def test_multiple_custom_keys(self):
        """Multiple custom task types should all be preserved."""
        base = {
            "reasoning": [],
            "doc_step": [],
            "readfulldocument": [],
            "readfulltext": [],
            "vl_analysis": [[{"role": "user", "content": "vl"}]],
            "ocr_extraction": [[{"role": "user", "content": "ocr"}]],
            "table_parsing": [[{"role": "user", "content": "table"}]],
        }
        ts = convert_base_train_sample(base, "sys", "hash")
        d = ts.to_dict()

        assert "vl_analysis" in d
        assert "ocr_extraction" in d
        assert "table_parsing" in d
