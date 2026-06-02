#!/usr/bin/env python3
"""
exaone/batch_runner_pool.py — ExaoneBatchRunnerPool (multi-host)

Multi-host extension of ``ExaoneBatchRunner``: instead of N worker
processes pointed at a single ``EXAONE_BASE_URL``, this runner spawns
``sum(host.n_concurrent)`` worker processes, each bound to a specific
vLLM host from a YAML config. Each worker sets ``EXAONE_BASE_URL`` in
its own process environment and clears the ``load_config`` lru_cache,
so:

  * The worker's ``ExaoneAgent`` instances target the assigned host.
  * Tool-internal LLM calls (``ReadFullDocument`` extractor,
    ``web_extract`` summarizer) follow the same host via the
    auxiliary_client main_runtime fallback in
    ``agent/auxiliary_client.py``.

Output structure, checkpointing, resume semantics, and trace output
are identical to ``exaone/batch_runner.py``.

Usage:
    HERMES_EXAONE_AGENT=1 uv run python exaone/batch_runner_pool.py \\
        --dataset_file=gen.jsonl --batch_size=10 --run_name=sft_v1 \\
        --host_config=configs/hosts.yaml

    # Resume interrupted run
    HERMES_EXAONE_AGENT=1 uv run python exaone/batch_runner_pool.py \\
        --dataset_file=gen.jsonl --batch_size=10 --run_name=sft_v1 \\
        --host_config=configs/hosts.yaml --resume

    # Disable reasoning globally
    HERMES_EXAONE_AGENT=1 uv run python exaone/batch_runner_pool.py \\
        --dataset_file=gen.jsonl --batch_size=10 --run_name=sft_v1 \\
        --host_config=configs/hosts.yaml --reasoning=false
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import traceback
from dataclasses import dataclass
from datetime import datetime
from multiprocessing import JoinableQueue, Process, Queue
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Make repo root importable when invoked as a script (matches batch_runner.py).
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
    ALL_POSSIBLE_TOOLS as _HERMES_BUILTIN_TOOLS,
    _normalize_tool_error_counts,
    _normalize_tool_stats,
)
from exaone.batch_runner import (
    ExaoneBatchRunner,
    _exaone_process_single_prompt,
)
from exaone.config import bootstrap_gateway_env

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HostSlot:
    """A single worker slot bound to one vLLM host."""

    worker_id: int
    host: str
    base_url: str
    model: str
    api_key: str


# ---------------------------------------------------------------------------
# Host-config loading
# ---------------------------------------------------------------------------


def _load_host_config(path: str) -> List[HostSlot]:
    """Parse ``configs/hosts.yaml`` into a flat list of worker slots.

    Each host expands to ``n_concurrent`` entries — one per worker process —
    with ``model`` / ``api_key`` / port resolved from the YAML defaults or
    overridden per host. Order is preserved so workers spawn deterministically.
    """
    import yaml  # pyyaml is already a project dep

    cfg_path = Path(path)
    if not cfg_path.exists():
        raise FileNotFoundError(f"host_config not found: {cfg_path}")

    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"host_config must be a YAML mapping: {cfg_path}")

    default_model = str(raw.get("model") or "").strip()
    default_api_key = str(raw.get("api_key") or "EMPTY").strip() or "EMPTY"
    default_port = int(raw.get("port") or 8000)
    hosts = raw.get("hosts") or []
    if not isinstance(hosts, list) or not hosts:
        raise ValueError(f"host_config 'hosts' must be a non-empty list: {cfg_path}")

    slots: List[HostSlot] = []
    for entry in hosts:
        if not isinstance(entry, dict):
            raise ValueError(f"host entry must be a mapping, got: {entry!r}")
        host = str(entry.get("host") or "").strip()
        if not host:
            raise ValueError(f"host entry missing 'host': {entry!r}")
        n_concurrent = int(entry.get("n_concurrent") or 1)
        if n_concurrent < 1:
            raise ValueError(f"host {host}: n_concurrent must be >= 1")
        port = int(entry.get("port") or default_port)
        model = str(entry.get("model") or default_model).strip()
        if not model:
            raise ValueError(
                f"host {host}: model must be set either at root or on the host entry"
            )
        api_key = str(entry.get("api_key") or default_api_key).strip() or "EMPTY"
        # Use https + standard /v1 for OpenAI; http+port for local vLLM.
        if host == "api.openai.com":
            base_url = "https://api.openai.com/v1"
            if api_key == "PLACEHOLDER_USE_ENV" or api_key == "EMPTY":
                import os as _os
                api_key = _os.environ.get("OPENAI_API_KEY", "EMPTY")
        else:
            base_url = f"http://{host}:{port}/v1"
        for _ in range(n_concurrent):
            slots.append(HostSlot(
                worker_id=len(slots),
                host=host,
                base_url=base_url,
                model=model,
                api_key=api_key,
            ))

    return slots


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------


_SENTINEL = None  # JoinableQueue stop signal


# Hermes ALL_POSSIBLE_TOOLS is derived from TOOL_TO_TOOLSET_MAP which does
# not register the exaone-side tools (parse_web_and_doc, doc_search, etc.).
# They would be wrongly filtered as "corrupted" at trajectories.jsonl merge
# time without this extension.
_EXAONE_EXTRA_TOOLS = frozenset({
    "parse_web_and_doc",
    "doc_search",
    "list_documents",
    "get_document_chunks",
    "ReadFullDocument",
})
ALL_POSSIBLE_TOOLS = frozenset(_HERMES_BUILTIN_TOOLS) | _EXAONE_EXTRA_TOOLS


def _worker_loop(
    slot: HostSlot,
    task_queue: JoinableQueue,
    result_queue: Queue,
    config: Dict[str, Any],
) -> None:
    """Worker process body.

    Pins this process to ``slot.base_url`` by exporting EXAONE_BASE_URL /
    EXAONE_MODEL / EXAONE_API_KEY before any exaone module reads config,
    then drains the task queue one prompt at a time. ``load_config``'s
    ``lru_cache`` is cleared so the freshly-set env vars take effect even
    if the parent process happened to materialize the cache before fork.
    """
    os.environ["EXAONE_BASE_URL"] = slot.base_url
    os.environ["EXAONE_MODEL"] = slot.model
    os.environ["EXAONE_API_KEY"] = slot.api_key
    os.environ.setdefault("HERMES_EXAONE_AGENT", "1")

    try:
        from exaone.config import load_config as _load_config

        _load_config.cache_clear()
    except Exception:  # pragma: no cover — defensive
        pass

    while True:
        task = task_queue.get()
        if task is _SENTINEL:
            task_queue.task_done()
            return
        prompt_index, prompt_data, batch_num = task
        try:
            result = _exaone_process_single_prompt(
                prompt_index, prompt_data, batch_num, config
            )
        except Exception as exc:
            result = {
                "success": False,
                "prompt_index": prompt_index,
                "error": f"worker {slot.worker_id} ({slot.host}) crashed: {exc}",
                "trajectory": None,
                "tool_stats": {},
                "toolsets_used": [],
                "metadata": {
                    "batch_num": batch_num,
                    "timestamp": datetime.now().isoformat(),
                    "host": slot.host,
                },
            }
        # Tag result with the host that produced it (debug + per-host stats).
        result.setdefault("metadata", {})["host"] = slot.host
        result_queue.put((batch_num, result))
        task_queue.task_done()


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class ExaoneBatchRunnerPool(ExaoneBatchRunner):
    """ExaoneBatchRunner variant that distributes prompts across a host pool."""

    def __init__(
        self,
        dataset_file: str,
        batch_size: int,
        run_name: str,
        host_config: str,
        max_iterations: int = 10,
        verbose: bool = False,
        max_samples: int = None,
        reasoning: bool = True,
    ):
        self.host_slots: List[HostSlot] = _load_host_config(host_config)
        self.host_config_path = host_config

        # Per-worker base_url/api_key come from each slot's env injection — the
        # parent's fields are unused on this path but kept to satisfy the API.
        super().__init__(
            dataset_file=dataset_file,
            batch_size=batch_size,
            run_name=run_name,
            max_iterations=max_iterations,
            base_url=None,
            api_key=None,
            num_workers=len(self.host_slots),
            verbose=verbose,
            max_samples=max_samples,
            reasoning=reasoning,
        )

        # Re-print the worker breakdown so the user sees the pool layout.
        host_counts = self._host_counts()
        print(f"   Host pool ({len(host_counts)} hosts, {len(self.host_slots)} total workers):")
        for host, count in host_counts.items():
            print(f"     - {host} × {count}")

    def _host_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for slot in self.host_slots:
            counts[slot.host] = counts.get(slot.host, 0) + 1
        return counts

    def run(self, resume: bool = False):
        """Run batch processing distributed across the host pool."""
        print("\n" + "=" * 70)
        print("🚀 Starting Exaone Batch Processing (multi-host pool)")
        print("=" * 70)

        completed_prompt_texts = set()
        if resume:
            completed_prompt_texts = self._scan_completed_prompts_by_content()
            if completed_prompt_texts:
                print(
                    f"   Found {len(completed_prompt_texts)} already-completed prompts "
                    "by content matching"
                )

        if resume and completed_prompt_texts:
            filtered_entries, skipped_indices = self._filter_dataset_by_completed(
                completed_prompt_texts
            )
            if not filtered_entries:
                print("\n✅ All prompts have already been processed!")
                return

            batches_to_process = [
                filtered_entries[i : i + self.batch_size]
                for i in range(0, len(filtered_entries), self.batch_size)
            ]
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

        # base_url/api_key come from per-worker env injection — omit here so
        # _exaone_process_single_prompt's `is not None` guards skip them.
        config = {
            "reasoning": self.reasoning,
            "max_iterations": self.max_iterations,
            "verbose": self.verbose,
        }

        completed_prompts_set = (
            set(checkpoint_data.get("completed_prompts", [])) if resume else set()
        )
        total_tool_stats: Dict[str, Dict[str, int]] = {}
        host_prompt_counts: Dict[str, int] = {}
        start_time = time.time()

        # Materialize the (batch_num, prompt_index, prompt_data) work list.
        tasks: List[Tuple[int, Dict[str, Any], int]] = []
        for batch_num, batch_data in enumerate(self.batches):
            for prompt_index, prompt_data in batch_data:
                if prompt_index in completed_prompts_set:
                    continue
                tasks.append((prompt_index, prompt_data, batch_num))

        if not tasks:
            print("\n✅ Nothing to process (all prompts already completed).")
            return

        host_counts = self._host_counts()
        print(
            f"\n🔧 Spawning {len(self.host_slots)} worker processes across "
            f"{len(host_counts)} hosts..."
        )

        task_queue: JoinableQueue = JoinableQueue()
        result_queue: Queue = Queue()

        workers: List[Process] = []
        for slot in self.host_slots:
            p = Process(
                target=_worker_loop,
                args=(slot, task_queue, result_queue, config),
                name=f"ExaoneWorker-{slot.worker_id}@{slot.host}",
                daemon=False,
            )
            p.start()
            workers.append(p)

        for task in tasks:
            task_queue.put(task)
        for _ in workers:
            task_queue.put(_SENTINEL)

        total_reasoning_stats = {
            "total_assistant_turns": 0,
            "turns_with_reasoning": 0,
            "turns_without_reasoning": 0,
        }

        console = Console(force_terminal=True)
        try:
            root_logger = logging.getLogger()
            original_level = root_logger.level
            root_logger.setLevel(logging.WARNING)
            with Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]📝 Prompts"),
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
                pbar = progress.add_task("Processing", total=len(tasks))

                processed = 0
                while processed < len(tasks):
                    batch_num, result = result_queue.get()
                    processed += 1
                    prompt_index = result.get("prompt_index")
                    host_label = (result.get("metadata") or {}).get("host", "?")
                    host_prompt_counts[host_label] = (
                        host_prompt_counts.get(host_label, 0) + 1
                    )

                    if result.get("success") and result.get("trajectory"):
                        raw_tool_stats = result.get("tool_stats", {})
                        tool_stats = _normalize_tool_stats(raw_tool_stats)
                        raw_error_counts = {
                            name: stats.get("failure", 0)
                            for name, stats in raw_tool_stats.items()
                        }
                        tool_error_counts = _normalize_tool_error_counts(
                            raw_error_counts
                        )
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
                        batch_path = self.output_dir / f"batch_{batch_num}.jsonl"
                        with open(batch_path, "a", encoding="utf-8") as f:
                            f.write(json.dumps(trajectory_entry, ensure_ascii=False) + "\n")
                        completed_prompts_set.add(prompt_index)

                    # Aggregate tool stats across the whole run.
                    for tool_name, stats in result.get("tool_stats", {}).items():
                        if tool_name not in total_tool_stats:
                            total_tool_stats[tool_name] = {
                                "count": 0,
                                "success": 0,
                                "failure": 0,
                            }
                        total_tool_stats[tool_name]["count"] += stats["count"]
                        total_tool_stats[tool_name]["success"] += stats["success"]
                        total_tool_stats[tool_name]["failure"] += stats["failure"]

                    for k in total_reasoning_stats:
                        total_reasoning_stats[k] += result.get("reasoning_stats", {}).get(k, 0)

                    if result.get("success") and result.get("trajectory"):
                        flag = "⚠️" if result.get("partial") else "✅"
                        progress.console.print(
                            f"   {flag} prompt {prompt_index} [host {host_label}]"
                        )
                    else:
                        progress.console.print(
                            f"   ❌ prompt {prompt_index} failed "
                            f"[host {host_label}]: {result.get('error', '?')[:120]}"
                        )

                    progress.update(pbar, advance=1)

                    # Incremental checkpoint every 10 completions.
                    if processed % 10 == 0:
                        try:
                            checkpoint_data["completed_prompts"] = sorted(
                                completed_prompts_set
                            )
                            checkpoint_data["last_updated"] = (
                                datetime.now().isoformat()
                            )
                            self._save_checkpoint(checkpoint_data)
                        except Exception as ckpt_err:
                            print(
                                f"⚠️  Warning: incremental checkpoint save failed: "
                                f"{ckpt_err}"
                            )
        finally:
            root_logger.setLevel(original_level)

        # Drain queue + shut workers down cleanly.
        task_queue.join()
        for p in workers:
            p.join(timeout=10)
            if p.is_alive():
                p.terminate()

        try:
            checkpoint_data["completed_prompts"] = sorted(completed_prompts_set)
            checkpoint_data["last_updated"] = datetime.now().isoformat()
            self._save_checkpoint(checkpoint_data)
        except Exception as ckpt_err:
            print(f"⚠️  Warning: final checkpoint save failed: {ckpt_err}")

        # Roll up success/failure rates.
        for tool_name, stats in total_tool_stats.items():
            calls = stats["success"] + stats["failure"]
            if calls > 0:
                stats["success_rate"] = round(stats["success"] / calls * 100, 2)
                stats["failure_rate"] = round(stats["failure"] / calls * 100, 2)
            else:
                stats["success_rate"] = 0.0
                stats["failure_rate"] = 0.0

        # Merge per-batch JSONL into trajectories.jsonl (same as single-host runner).
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
                            invalid_tools = [
                                k for k in tool_stats if k not in ALL_POSSIBLE_TOOLS
                            ]
                            if invalid_tools:
                                filtered_entries_count += 1
                                preview = invalid_tools[0][:50]
                                print(
                                    f"   ⚠️  Filtering corrupted entry "
                                    f"(batch {batch_num_str}): invalid tool '{preview}'"
                                )
                                continue
                            outfile.write(line)
                        except json.JSONDecodeError:
                            filtered_entries_count += 1
                            print(
                                f"   ⚠️  Filtering invalid JSON entry "
                                f"(batch {batch_num_str})"
                            )

        if filtered_entries_count > 0:
            print(
                f"⚠️  Filtered {filtered_entries_count} corrupted entries out of "
                f"{total_entries} total"
            )
        print(
            f"✅ Combined {batch_files_found} batch files into trajectories.jsonl "
            f"({total_entries - filtered_entries_count} entries)"
        )

        final_stats = {
            "run_name": self.run_name,
            "reasoning": self.reasoning,
            "host_config": self.host_config_path,
            "total_workers": len(self.host_slots),
            "host_counts": host_counts,
            "prompts_per_host": host_prompt_counts,
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
        print("📊 EXAONE BATCH PROCESSING COMPLETE (multi-host)")
        print("=" * 70)
        print(f"✅ Prompts processed this run: {len(tasks)}")
        print(
            f"✅ Total trajectories in merged file: "
            f"{total_entries - filtered_entries_count}"
        )
        print(f"✅ Total batch files merged: {batch_files_found}")
        print(f"⏱️  Total duration: {round(time.time() - start_time, 2)}s")

        print("\n🖧  Prompts per host:")
        for host, count in sorted(host_prompt_counts.items()):
            print(f"   {host:<20} {count}")

        print("\n📈 Tool Usage Statistics:")
        print("-" * 70)
        if total_tool_stats:
            sorted_tools = sorted(
                total_tool_stats.items(), key=lambda x: x[1]["count"], reverse=True
            )
            print(
                f"{'Tool Name':<25} {'Count':<10} {'Success':<10} "
                f"{'Failure':<10} {'Success Rate':<12}"
            )
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
        print("   - Exaone traces: <project-root>/logs/exaone_traces/")


def main(
    dataset_file: str = None,
    batch_size: int = None,
    run_name: str = None,
    host_config: str = None,
    max_turns: int = 10,
    verbose: bool = False,
    resume: bool = False,
    reasoning: bool = True,
    max_samples: int = None,
):
    """Run Exaone multi-host batch processing.

    Args:
        dataset_file (str): JSONL with 'prompt' (and optional 'qa_mode' / 'toolset' / 'reasoning').
        batch_size (int): Number of prompts per batch (controls per-batch_*.jsonl file size).
        run_name (str): Run name (used for output directory + checkpoint).
        host_config (str): YAML host pool config (host/n_concurrent + model/api_key/port).
        max_turns (int): Max tool-calling iterations per prompt (default: 10).
        verbose (bool): Verbose logging (default: False).
        resume (bool): Resume from checkpoint (default: False).
        reasoning (bool): Global enable_thinking on/off (per-row 'reasoning' overrides).
        max_samples (int): Only process first N samples (optional).

    Examples:
        HERMES_EXAONE_AGENT=1 uv run python exaone/batch_runner_pool.py \\
            --dataset_file=gen.jsonl --batch_size=10 --run_name=sft_v1 \\
            --host_config=configs/hosts.yaml

        HERMES_EXAONE_AGENT=1 uv run python exaone/batch_runner_pool.py \\
            --dataset_file=gen.jsonl --batch_size=10 --run_name=sft_v1 \\
            --host_config=configs/hosts.yaml --resume
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
    if not host_config:
        print("❌ Error: --host_config is required")
        return

    bootstrap_gateway_env()

    # fire parses --reasoning=false as the string 'false' (truthy), so convert manually.
    if isinstance(reasoning, str):
        reasoning = reasoning.lower() not in ("false", "0", "no", "off")

    try:
        runner = ExaoneBatchRunnerPool(
            dataset_file=dataset_file,
            batch_size=batch_size,
            run_name=run_name,
            host_config=host_config,
            max_iterations=max_turns,
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
