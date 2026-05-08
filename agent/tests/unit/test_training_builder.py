"""Unit tests for domain/training — TrainingSampleBuilder."""

import pytest

from agent.domain.reasoning.events import (
    DocSummaryCompleted,
    StepCompleted,
    ToolExtractionCompleted,
)
from agent.domain.training.builder import TrainingSampleBuilder


# ── Fixtures ────────────────────────────────────────────────


@pytest.fixture
def builder():
    return TrainingSampleBuilder(
        user_query="What is revenue?",
        filenames=["report.pdf"],
        df_idx=0,
    )


# ── record_doc_step ─────────────────────────────────────────


class TestDocStep:
    def test_record(self, builder):
        event = DocSummaryCompleted(prompt="Summarize", summary="Revenue is $10B")
        builder.record_doc_step(event)
        sample = builder.build()

        assert len(sample["doc_step"]) == 2
        assert sample["doc_step"][0] == {
            "role": "user",
            "content": "Summarize",
            "loss_masking": True,
        }
        assert sample["doc_step"][1] == {
            "role": "assistant",
            "content": "Revenue is $10B",
            "loss_masking": False,
        }

    def test_overwrite(self, builder):
        builder.record_doc_step(DocSummaryCompleted(prompt="p1", summary="s1"))
        builder.record_doc_step(DocSummaryCompleted(prompt="p2", summary="s2"))
        sample = builder.build()

        # Second call overwrites
        assert sample["doc_step"][0]["content"] == "p2"
        assert sample["doc_step"][1]["content"] == "s2"


# ── record_reasoning_turn ───────────────────────────────────


class TestReasoning:
    def test_single_turn(self, builder):
        event = StepCompleted(
            action_state=[
                {"role": "system", "content": "sys prompt"},
                {"role": "user", "content": "user msg"},
            ],
            response="<final_answer>42</final_answer>",
            step_number=2,
        )
        builder.record_reasoning_turn(event)
        sample = builder.build()

        assert len(sample["reasoning"]) == 1
        turn = sample["reasoning"][0]
        # All action_state turns have loss_masking=True
        assert turn[0]["loss_masking"] is True
        assert turn[1]["loss_masking"] is True
        # Assistant response has loss_masking=False
        assert turn[-1]["role"] == "assistant"
        assert turn[-1]["loss_masking"] is False
        assert turn[-1]["content"] == "<final_answer>42</final_answer>"

    def test_multi_turn(self, builder):
        for i in range(3):
            event = StepCompleted(
                action_state=[{"role": "user", "content": f"turn {i}"}],
                response=f"response {i}",
                step_number=i + 1,
            )
            builder.record_reasoning_turn(event)

        sample = builder.build()
        assert len(sample["reasoning"]) == 3

    def test_loss_masking(self, builder):
        """Every turn in action_state gets loss_masking=True."""
        event = StepCompleted(
            action_state=[
                {"role": "system", "content": "s"},
                {"role": "user", "content": "u"},
                {"role": "assistant", "content": "a"},
            ],
            response="final",
            step_number=1,
        )
        builder.record_reasoning_turn(event)
        turn = builder.build()["reasoning"][0]

        for msg in turn[:-1]:
            assert msg["loss_masking"] is True
        assert turn[-1]["loss_masking"] is False


# ── record_extraction ───────────────────────────────────────


class TestExtraction:
    def test_readfulldocument(self, builder):
        event = ToolExtractionCompleted(
            tool_name="ReadFullDocument",
            messages=[{"role": "user", "content": "Read doc1"}],
            result="Document content here",
        )
        builder.record_extraction(event)
        sample = builder.build()

        assert len(sample["readfulldocument"]) == 1
        entry = sample["readfulldocument"][0]
        assert entry[0]["role"] == "user"
        assert entry[0]["loss_masking"] is True
        assert entry[1]["role"] == "assistant"
        assert entry[1]["content"] == "Document content here"
        assert entry[1]["loss_masking"] is False

    def test_readfulltext(self, builder):
        event = ToolExtractionCompleted(
            tool_name="ReadFullText",
            messages=[{"role": "user", "content": "Extract text"}],
            result="Extracted text",
        )
        builder.record_extraction(event)
        sample = builder.build()

        assert len(sample["readfulltext"]) == 1

    def test_unknown_tool(self, builder):
        event = ToolExtractionCompleted(
            tool_name="UnknownTool",
            messages=[{"role": "user", "content": "msg"}],
            result="result",
        )
        builder.record_extraction(event)
        sample = builder.build()

        # Unknown tools are silently ignored
        assert len(sample["readfulldocument"]) == 0
        assert len(sample["readfulltext"]) == 0

    def test_empty_messages(self, builder):
        event = ToolExtractionCompleted(
            tool_name="ReadFullDocument",
            messages=[],
            result="content",
        )
        builder.record_extraction(event)
        sample = builder.build()

        assert len(sample["readfulldocument"]) == 1
        entry = sample["readfulldocument"][0]
        # Only the assistant message
        assert len(entry) == 1
        assert entry[0]["role"] == "assistant"


# ── build ───────────────────────────────────────────────────


class TestBuild:
    def test_full(self, builder):
        builder.record_doc_step(DocSummaryCompleted(prompt="p", summary="s"))
        builder.record_reasoning_turn(
            StepCompleted(
                action_state=[{"role": "user", "content": "q"}],
                response="ans",
                step_number=1,
            )
        )
        builder.record_extraction(
            ToolExtractionCompleted(
                tool_name="ReadFullDocument",
                messages=[{"role": "user", "content": "read"}],
                result="doc content",
            )
        )

        sample = builder.build()
        assert sample["df_idx"] == 0
        assert sample["user_query"] == "What is revenue?"
        assert sample["filenames"] == ["report.pdf"]
        assert len(sample["doc_step"]) == 2
        assert len(sample["reasoning"]) == 1
        assert len(sample["readfulldocument"]) == 1

    def test_empty(self):
        b = TrainingSampleBuilder(user_query="q", filenames=["f.pdf"])
        sample = b.build()

        assert sample["user_query"] == "q"
        assert sample["reasoning"] == []
        assert sample["readfulldocument"] == []
        assert sample["readfulltext"] == []
        assert sample["doc_step"] == []

    def test_immutability(self, builder):
        """build() returns a deep copy — mutations don't affect builder."""
        sample1 = builder.build()
        sample1["reasoning"].append("garbage")

        sample2 = builder.build()
        assert sample2["reasoning"] == []
