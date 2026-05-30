#!/usr/bin/env python3
"""
exaone/batch_runner.py — ExaoneBatchRunner

BatchRunner subclass that drives ExaoneAgent directly (no gateway).
JSONL rows may carry `qa_mode` and/or `toolset` fields alongside `prompt`.
For multi-turn rows, provide one of:
  - `conversation_history` (or `history`) + `prompt`
  - `messages` (OpenAI-style list); runner uses the last user turn as prompt
    and all prior messages as conversation history.
Trace logging is handled automatically by ExaoneAgent; this runner
adds batch checkpointing, resume, and trajectory JSONL output.

Usage:
    HERMES_EXAONE_AGENT=1 python exaone/batch_runner.py \\
        --dataset_file=data.jsonl --batch_size=10 --run_name=my_run

    # Resume interrupted run
    HERMES_EXAONE_AGENT=1 python exaone/batch_runner.py \\
        --dataset_file=data.jsonl --batch_size=10 --run_name=my_run --resume

    # Disable reasoning globally
    HERMES_EXAONE_AGENT=1 python exaone/batch_runner.py \\
        --dataset_file=data.jsonl --batch_size=10 --run_name=my_run --reasoning=false
"""

import sys
import json
import logging
import time
import traceback
from datetime import datetime
from multiprocessing import Lock, Pool
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# When run as a script, Python adds exaone/ to sys.path[0], which shadows the
# top-level batch_runner module. Insert the repo root first to fix this.
_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import fire
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
)

from batch_runner import (
    BatchRunner,
    _extract_reasoning_stats,
    _extract_tool_stats,
    _normalize_tool_error_counts,
    _normalize_tool_stats,
)
from exaone.config import bootstrap_gateway_env
from exaone.qa_modes import validate_exclusive_modes

logger = logging.getLogger(__name__)


def _normalize_history_messages(raw: Any) -> List[Dict[str, Any]]:
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return []
        raw = json.loads(raw)
    if not isinstance(raw, list):
        raise ValueError("history/messages must be a list of dicts")
    out: List[Dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("history/messages entries must be dicts")
        role = item.get("role")
        if not isinstance(role, str):
            raise ValueError("history/messages entries require string 'role'")
        msg = dict(item)
        if "content" not in msg:
            msg["content"] = ""
        out.append(msg)
    return out


def _resolve_prompt_and_history(prompt_data: Dict[str, Any]) -> Tuple[str, List[Dict[str, Any]]]:
    prompt = prompt_data.get("prompt")
    history_raw = (
        prompt_data.get("conversation_history")
        if "conversation_history" in prompt_data
        else prompt_data.get("history")
    )
    if history_raw is not None:
        history = _normalize_history_messages(history_raw)
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt is required when conversation_history/history is provided")
        return prompt, history

    messages_raw = prompt_data.get("messages")
    if messages_raw is None:
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt is required")
        return prompt, []

    messages = _normalize_history_messages(messages_raw)
    last_user_idx = -1
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get("role") == "user":
            last_user_idx = i
            break
    if last_user_idx < 0:
        raise ValueError("messages must include at least one user turn")
    resolved_prompt = messages[last_user_idx].get("content", "")
    if not isinstance(resolved_prompt, str):
        resolved_prompt = str(resolved_prompt)
    if isinstance(prompt, str) and prompt.strip():
        resolved_prompt = prompt
    elif not resolved_prompt.strip():
        raise ValueError("last user message content is empty; provide prompt explicitly")
    history = messages[:last_user_idx]
    return resolved_prompt, history


def _exaone_process_single_prompt(
    prompt_index: int,
    prompt_data: Dict[str, Any],
    batch_num: int,
    config: Dict[str, Any],
) -> Dict[str, Any]:
    """Process one prompt with ExaoneAgent. qa_mode and toolset come from prompt_data."""
    from exaone.agent import ExaoneAgent

    qa_mode = prompt_data.get("qa_mode")
    toolset = prompt_data.get("toolset")
    enabled_toolsets = prompt_data.get("enabled_toolsets")
    # Per-row reasoning overrides the CLI global; fall back to config if not specified
    reasoning = prompt_data.get("reasoning", config["reasoning"])

    # enabled_toolsets takes priority; qa_mode/toolset mutual-exclusivity still applies
    if enabled_toolsets is None:
        if qa_mode is None and toolset is None:
            qa_mode = "general"
        try:
            validate_exclusive_modes(toolset, qa_mode)
        except ValueError as e:
            return {
                "success": False,
                "prompt_index": prompt_index,
                "error": str(e),
                "trajectory": None,
                "tool_stats": {},
                "toolsets_used": [],
                "metadata": {"batch_num": batch_num, "timestamp": datetime.now().isoformat()},
            }

    try:
        extra = {}
        if config.get("base_url") is not None:
            extra["base_url"] = config["base_url"]
        if config.get("api_key") is not None:
            extra["api_key"] = config["api_key"]

        agent_kwargs = dict(
            reasoning=reasoning,
            max_iterations=config["max_iterations"],
            verbose_logging=config.get("verbose", False),
            **extra,
        )
        if enabled_toolsets is not None:
            agent_kwargs["enabled_toolsets"] = enabled_toolsets
        else:
            agent_kwargs["qa_mode"] = qa_mode
            agent_kwargs["toolset"] = toolset

        # SFT batch path: pin {language} in the system prompt to the
        # concrete batch language (e.g. "Korean") so generated reasoning
        # / answers are language-consistent. Omitting this kwarg keeps
        # the generic fallback — production serving relies on that.
        row_language = prompt_data.get("language")
        if row_language:
            agent_kwargs["language"] = row_language

        agent = ExaoneAgent(**agent_kwargs)

        prompt, conversation_history = _resolve_prompt_and_history(prompt_data)
        task_id = f"task_{prompt_index}"

        # Register per-task attachments and prepend the "[Attached documents]"
        # block to the user prompt so the agent sees ``[N] basename`` rows
        # instead of raw file paths.
        from exaone.docqa_tools._attachments import (
            Attachment,
            register_attachments,
            render_attachments_block,
        )

        raw_attachments = prompt_data.get("attachments") or []
        attachments: list[Attachment] = []
        for entry in raw_attachments:
            if not isinstance(entry, dict):
                continue
            try:
                attachments.append(Attachment(
                    idx=int(entry["idx"]),
                    file_path=str(entry["file_path"]),
                    filename=str(entry.get("filename") or entry["file_path"].split("/")[-1]),
                ))
            except (KeyError, TypeError, ValueError):
                continue
        if attachments:
            register_attachments(task_id=task_id, entries=attachments)
            block = render_attachments_block(attachments)
            prompt = f"{block}\n\n{prompt}"

        # Optional prewarm: simulate the production "user already has these docs
        # indexed" scenario by registering every attachment into the per-task
        # cache *before* the agent loop starts. The model's first list_documents
        # call will see them all parsed=True, so it can skip parse_web_and_doc
        # and go straight to doc_search / RFD. None of the prewarm calls appear
        # in the trajectory — only the model-issued tool calls do.
        if attachments and bool(prompt_data.get("prewarm", False)):
            import asyncio as _asyncio
            from exaone.parsing_tools.handle_parse_web_and_doc import (
                handle_parse_web_and_doc as _handle_parse_web_and_doc,
            )

            _prewarm_idxs = [a.idx for a in attachments]
            try:
                _asyncio.get_event_loop().run_until_complete(
                    _handle_parse_web_and_doc(
                        {"document_idx": _prewarm_idxs}, task_id=task_id
                    )
                )
            except RuntimeError:
                # No event loop in this worker thread — create one.
                _asyncio.run(
                    _handle_parse_web_and_doc(
                        {"document_idx": _prewarm_idxs}, task_id=task_id
                    )
                )

        result = agent.run_conversation(
            prompt, task_id=task_id, conversation_history=conversation_history
        )

        tool_stats = _extract_tool_stats(result["messages"])
        reasoning_stats = _extract_reasoning_stats(result["messages"])
        trajectory = agent._convert_to_trajectory_format(
            result["messages"], prompt, result["completed"]
        )

        if enabled_toolsets is not None:
            toolsets_used = [enabled_toolsets] if isinstance(enabled_toolsets, str) else list(enabled_toolsets)
        else:
            toolsets_used = list(toolset) if toolset else ([qa_mode] if qa_mode else [])

        return {
            "success": True,
            "prompt_index": prompt_index,
            "trajectory": trajectory,
            "tool_stats": tool_stats,
            "reasoning_stats": reasoning_stats,
            "completed": result["completed"],
            "partial": result.get("partial", False),
            "api_calls": result["api_calls"],
            "toolsets_used": toolsets_used,
            "metadata": {
                "batch_num": batch_num,
                "timestamp": datetime.now().isoformat(),
                "qa_mode": qa_mode,
                "toolset": toolset,
                "enabled_toolsets": enabled_toolsets,
            },
        }

    except Exception as e:
        print(f"❌ Error processing prompt {prompt_index}: {e}")
        if config.get("verbose"):
            traceback.print_exc()
        return {
            "success": False,
            "prompt_index": prompt_index,
            "error": str(e),
            "trajectory": None,
            "tool_stats": {},
            "toolsets_used": [],
            "metadata": {"batch_num": batch_num, "timestamp": datetime.now().isoformat()},
        }


def _exaone_process_batch_worker(args: Tuple) -> Dict[str, Any]:
    """Worker function to process a single batch of prompts via ExaoneAgent."""
    batch_num, batch_data, output_dir, completed_prompts_set, config = args

    output_dir = Path(output_dir)
    print(f"\n🔄 Batch {batch_num}: Starting ({len(batch_data)} prompts)")

    batch_output_file = output_dir / f"batch_{batch_num}.jsonl"

    prompts_to_process = [
        (idx, data) for idx, data in batch_data if idx not in completed_prompts_set
    ]

    if not prompts_to_process:
        print(f"✅ Batch {batch_num}: Already completed (skipping)")
        return {
            "batch_num": batch_num,
            "processed": 0,
            "skipped": len(batch_data),
            "tool_stats": {},
            "reasoning_stats": {},
            "completed_prompts": [],
        }

    print(
        f"   Processing {len(prompts_to_process)} prompts "
        f"(skipping {len(batch_data) - len(prompts_to_process)} already completed)"
    )

    batch_tool_stats: Dict[str, Dict[str, int]] = {}
    batch_reasoning_stats = {
        "total_assistant_turns": 0,
        "turns_with_reasoning": 0,
        "turns_without_reasoning": 0,
    }
    completed_in_batch: List[int] = []

    for prompt_index, prompt_data in prompts_to_process:
        result = _exaone_process_single_prompt(prompt_index, prompt_data, batch_num, config)

        if result["success"] and result["trajectory"]:
            raw_tool_stats = result.get("tool_stats", {})
            tool_stats = _normalize_tool_stats(raw_tool_stats)
            raw_error_counts = {
                name: stats.get("failure", 0) for name, stats in raw_tool_stats.items()
            }
            tool_error_counts = _normalize_tool_error_counts(raw_error_counts)

            trajectory_entry = {
                "prompt_index": prompt_index,
                "conversations": result["trajectory"],
                "metadata": result["metadata"],
                "completed": result["completed"],
                "partial": result.get("partial", False),
                "api_calls": result["api_calls"],
                "toolsets_used": result["toolsets_used"],
                "tool_stats": tool_stats,
                "tool_error_counts": tool_error_counts,
            }

            with open(batch_output_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(trajectory_entry, ensure_ascii=False) + "\n")

        for tool_name, stats in result.get("tool_stats", {}).items():
            if tool_name not in batch_tool_stats:
                batch_tool_stats[tool_name] = {"count": 0, "success": 0, "failure": 0}
            batch_tool_stats[tool_name]["count"] += stats["count"]
            batch_tool_stats[tool_name]["success"] += stats["success"]
            batch_tool_stats[tool_name]["failure"] += stats["failure"]

        for key in batch_reasoning_stats:
            batch_reasoning_stats[key] += result.get("reasoning_stats", {}).get(key, 0)

        if result["success"] and result["trajectory"]:
            completed_in_batch.append(prompt_index)
            status = "⚠️  partial" if result.get("partial") else "✅"
            print(f"   {status} Prompt {prompt_index} completed")
        else:
            print(f"   ❌ Prompt {prompt_index} failed (will retry on resume)")

    print(f"✅ Batch {batch_num}: Completed ({len(prompts_to_process)} prompts processed)")

    return {
        "batch_num": batch_num,
        "processed": len(prompts_to_process),
        "skipped": len(batch_data) - len(prompts_to_process),
        "tool_stats": batch_tool_stats,
        "reasoning_stats": batch_reasoning_stats,
        "completed_prompts": completed_in_batch,
    }


class ExaoneBatchRunner(BatchRunner):
    """BatchRunner subclass that uses ExaoneAgent with per-row qa_mode/toolset."""

    def __init__(
        self,
        dataset_file: str,
        batch_size: int,
        run_name: str,
        max_iterations: int = 10,
        base_url: str = None,
        api_key: str = None,
        num_workers: int = 4,
        verbose: bool = False,
        max_samples: int = None,
        reasoning: bool = True,
    ):
        self.reasoning = reasoning
        # Pass distribution="default" to satisfy base validation; it is never used
        # because we override run() to call _exaone_process_batch_worker instead.
        super().__init__(
            dataset_file=dataset_file,
            batch_size=batch_size,
            run_name=run_name,
            distribution="default",
            max_iterations=max_iterations,
            base_url=base_url,
            api_key=api_key,
            model="exaone",  # informational only; ExaoneAgent reads from config
            num_workers=num_workers,
            verbose=verbose,
            max_samples=max_samples,
        )

    def run(self, resume: bool = False):
        """Run batch processing using ExaoneAgent workers."""
        print("\n" + "=" * 70)
        print("🚀 Starting Exaone Batch Processing")
        print("=" * 70)

        completed_prompt_texts = set()
        if resume:
            completed_prompt_texts = self._scan_completed_prompts_by_content()
            if completed_prompt_texts:
                print(f"   Found {len(completed_prompt_texts)} already-completed prompts by content matching")

        if resume and completed_prompt_texts:
            filtered_entries, skipped_indices = self._filter_dataset_by_completed(completed_prompt_texts)

            if not filtered_entries:
                print("\n✅ All prompts have already been processed!")
                return

            batches_to_process = []
            for i in range(0, len(filtered_entries), self.batch_size):
                batches_to_process.append(filtered_entries[i : i + self.batch_size])
            self.batches = batches_to_process

            print("\n" + "=" * 70)
            print("📊 RESUME SUMMARY")
            print("=" * 70)
            print(f"   Original dataset size:     {len(self.dataset):,} prompts")
            print(f"   Already completed:         {len(skipped_indices):,} prompts")
            print("   ─────────────────────────────────────────")
            print(f"   🎯 RESUMING WITH:          {len(filtered_entries):,} prompts")
            print(f"   New batches created:       {len(batches_to_process)}")
            print("=" * 70 + "\n")

        checkpoint_data = self._load_checkpoint()
        if checkpoint_data.get("run_name") != self.run_name:
            checkpoint_data = {
                "run_name": self.run_name,
                "completed_prompts": [],
                "batch_stats": {},
                "last_updated": None,
            }

        config = {
            "reasoning": self.reasoning,
            "max_iterations": self.max_iterations,
            "base_url": self.base_url,
            "api_key": self.api_key,
            "verbose": self.verbose,
        }

        # resume=False means fresh run — ignore prior checkpoint's completed list
        completed_prompts_set = set(checkpoint_data.get("completed_prompts", [])) if resume else set()
        total_tool_stats: Dict[str, Dict[str, int]] = {}
        start_time = time.time()

        print(f"\n🔧 Initializing {self.num_workers} worker processes...")

        checkpoint_lock = Lock()

        with Pool(processes=self.num_workers) as pool:
            tasks = [
                (batch_num, batch_data, str(self.output_dir), completed_prompts_set, config)
                for batch_num, batch_data in enumerate(self.batches)
            ]

            print(f"✅ Created {len(tasks)} batch tasks")
            print("🚀 Starting parallel batch processing...\n")

            results = []
            console = Console(force_terminal=True)
            with Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]📦 Batches"),
                BarColumn(bar_width=40),
                MofNCompleteColumn(),
                TextColumn("•"),
                TimeRemainingColumn(),
                console=console,
                refresh_per_second=2,
                transient=False,
                redirect_stdout=False,
                redirect_stderr=False,
            ) as progress:
                task = progress.add_task("Processing", total=len(tasks))

                root_logger = logging.getLogger()
                original_level = root_logger.level
                root_logger.setLevel(logging.WARNING)

                try:
                    for result in pool.imap_unordered(_exaone_process_batch_worker, tasks):
                        results.append(result)
                        progress.update(task, advance=1)

                        try:
                            batch_num = result.get("batch_num")
                            completed = result.get("completed_prompts", []) or []
                            completed_prompts_set.update(completed)

                            if isinstance(batch_num, int):
                                checkpoint_data.setdefault("batch_stats", {})[str(batch_num)] = {
                                    "processed": result.get("processed", 0),
                                    "skipped": result.get("skipped", 0),
                                }

                            checkpoint_data["completed_prompts"] = sorted(completed_prompts_set)
                            self._save_checkpoint(checkpoint_data, lock=checkpoint_lock)
                        except Exception as ckpt_err:
                            print(f"⚠️  Warning: Failed to save incremental checkpoint: {ckpt_err}")
                except Exception as e:
                    logger.error("Batch worker failed: %s", e, exc_info=True)
                    raise
                finally:
                    root_logger.setLevel(original_level)

        total_reasoning_stats = {
            "total_assistant_turns": 0,
            "turns_with_reasoning": 0,
            "turns_without_reasoning": 0,
        }

        for batch_result in results:
            for tool_name, stats in batch_result.get("tool_stats", {}).items():
                if tool_name not in total_tool_stats:
                    total_tool_stats[tool_name] = {"count": 0, "success": 0, "failure": 0}
                total_tool_stats[tool_name]["count"] += stats["count"]
                total_tool_stats[tool_name]["success"] += stats["success"]
                total_tool_stats[tool_name]["failure"] += stats["failure"]

            for key in total_reasoning_stats:
                total_reasoning_stats[key] += batch_result.get("reasoning_stats", {}).get(key, 0)

        try:
            checkpoint_data["completed_prompts"] = sorted(completed_prompts_set)
            self._save_checkpoint(checkpoint_data, lock=checkpoint_lock)
        except Exception as ckpt_err:
            print(f"⚠️  Warning: Failed to save final checkpoint: {ckpt_err}")

        for tool_name in total_tool_stats:
            stats = total_tool_stats[tool_name]
            total_calls = stats["success"] + stats["failure"]
            if total_calls > 0:
                stats["success_rate"] = round(stats["success"] / total_calls * 100, 2)
                stats["failure_rate"] = round(stats["failure"] / total_calls * 100, 2)
            else:
                stats["success_rate"] = 0.0
                stats["failure_rate"] = 0.0

        # Combine all batch files into trajectories.jsonl
        from batch_runner import ALL_POSSIBLE_TOOLS

        combined_file = self.output_dir / "trajectories.jsonl"
        print(f"\n📦 Combining ALL batch files into {combined_file.name}...")

        total_entries = 0
        filtered_entries_count = 0
        batch_files_found = 0

        all_batch_files = sorted(self.output_dir.glob("batch_*.jsonl"))

        with open(combined_file, "w", encoding="utf-8") as outfile:
            for batch_file in all_batch_files:
                batch_files_found += 1
                batch_num_str = batch_file.stem.split("_")[1]

                with open(batch_file, "r", encoding="utf-8") as infile:
                    for line in infile:
                        total_entries += 1
                        try:
                            data = json.loads(line)
                            tool_stats = data.get("tool_stats", {})
                            invalid_tools = [k for k in tool_stats if k not in ALL_POSSIBLE_TOOLS]
                            if invalid_tools:
                                filtered_entries_count += 1
                                preview = invalid_tools[0][:50]
                                print(
                                    f"   ⚠️  Filtering corrupted entry (batch {batch_num_str}): "
                                    f"invalid tool '{preview}'"
                                )
                                continue
                            outfile.write(line)
                        except json.JSONDecodeError:
                            filtered_entries_count += 1
                            print(f"   ⚠️  Filtering invalid JSON entry (batch {batch_num_str})")

        if filtered_entries_count > 0:
            print(f"⚠️  Filtered {filtered_entries_count} corrupted entries out of {total_entries} total")
        print(
            f"✅ Combined {batch_files_found} batch files into trajectories.jsonl "
            f"({total_entries - filtered_entries_count} entries)"
        )

        final_stats = {
            "run_name": self.run_name,
            "reasoning": self.reasoning,
            "total_prompts": len(self.dataset),
            "total_batches": len(self.batches),
            "batch_size": self.batch_size,
            "completed_at": datetime.now().isoformat(),
            "duration_seconds": round(time.time() - start_time, 2),
            "tool_statistics": total_tool_stats,
            "reasoning_statistics": total_reasoning_stats,
        }

        with open(self.stats_file, "w", encoding="utf-8") as f:
            json.dump(final_stats, f, indent=2, ensure_ascii=False)

        print("\n" + "=" * 70)
        print("📊 EXAONE BATCH PROCESSING COMPLETE")
        print("=" * 70)
        print(f"✅ Prompts processed this run: {sum(r.get('processed', 0) for r in results)}")
        print(f"✅ Total trajectories in merged file: {total_entries - filtered_entries_count}")
        print(f"✅ Total batch files merged: {batch_files_found}")
        print(f"⏱️  Total duration: {round(time.time() - start_time, 2)}s")

        print("\n📈 Tool Usage Statistics:")
        print("-" * 70)
        if total_tool_stats:
            sorted_tools = sorted(
                total_tool_stats.items(), key=lambda x: x[1]["count"], reverse=True
            )
            print(f"{'Tool Name':<25} {'Count':<10} {'Success':<10} {'Failure':<10} {'Success Rate':<12}")
            print("-" * 70)
            for tool_name, stats in sorted_tools:
                if stats["count"] == 0:
                    continue
                print(
                    f"{tool_name:<25} "
                    f"{stats['count']:<10} "
                    f"{stats['success']:<10} "
                    f"{stats['failure']:<10} "
                    f"{stats['success_rate']:.1f}%"
                )
        else:
            print("No tool calls were made during this run.")

        print(f"\n💾 Results saved to: {self.output_dir}")
        print("   - Trajectories: trajectories.jsonl (combined)")
        print("   - Individual batches: batch_*.jsonl (for debugging)")
        print(f"   - Statistics: {self.stats_file.name}")
        print(f"   - Checkpoint: {self.checkpoint_file.name}")
        print(f"   - Exaone traces: ~/.hermes/exaone_traces/")


def main(
    dataset_file: str = None,
    batch_size: int = None,
    run_name: str = None,
    max_turns: int = 10,
    base_url: str = None,
    api_key: str = None,
    num_workers: int = 4,
    verbose: bool = False,
    resume: bool = False,
    reasoning: bool = True,
    max_samples: int = None,
):
    """
    Run Exaone batch processing from a JSONL dataset.

    Args:
        dataset_file (str): Path to JSONL file; each row needs 'prompt' (or 'messages') and optionally 'qa_mode' or 'toolset'
        batch_size (int): Number of prompts per batch
        run_name (str): Name for this run (used for output and checkpointing)
        max_turns (int): Maximum tool-calling iterations per prompt (default: 10)
        base_url (str): Override Exaone base URL (reads EXAONE_BASE_URL env var by default)
        api_key (str): Override Exaone API key (reads EXAONE_API_KEY env var by default)
        num_workers (int): Number of parallel worker processes (default: 4)
        verbose (bool): Enable verbose logging (default: False)
        resume (bool): Resume from checkpoint if run was interrupted (default: False)
        reasoning (bool): Enable reasoning/thinking tokens globally (default: True)
        max_samples (int): Only process the first N samples (optional)

    Examples:
        python exaone/batch_runner.py \\
            --dataset_file=data.jsonl --batch_size=10 --run_name=my_run

        python exaone/batch_runner.py \\
            --dataset_file=data.jsonl --batch_size=10 --run_name=my_run --resume

        python exaone/batch_runner.py \\
            --dataset_file=data.jsonl --batch_size=10 --run_name=my_run --reasoning=false
    """
    if not dataset_file:
        print("❌ Error: --dataset_file is required")
        return
    if not batch_size or batch_size < 1:
        print("❌ Error: --batch_size must be a positive integer")
        return
    if not run_name:
        print("❌ Error: --run_name is required")
        return

    bootstrap_gateway_env()

    # fire parses --reasoning=false as the string 'false' (truthy), so convert manually
    if isinstance(reasoning, str):
        reasoning = reasoning.lower() not in ("false", "0", "no", "off")

    try:
        runner = ExaoneBatchRunner(
            dataset_file=dataset_file,
            batch_size=batch_size,
            run_name=run_name,
            max_iterations=max_turns,
            base_url=base_url,
            api_key=api_key,
            num_workers=num_workers,
            verbose=verbose,
            max_samples=max_samples,
            reasoning=reasoning,
        )
        runner.run(resume=resume)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        if verbose:
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    fire.Fire(main)
