import asyncio

from exaone.compaction_tracer import (
    bind_run_dir,
    rename_last_post_compaction_force_finish,
    unbind_run_dir,
    write_auxiliary_compaction_triplet,
    write_compaction_triplet,
)


def test_auxiliary_triplet_sequence_is_unique_under_parallel_tasks(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    tok_dir, tok_seq = bind_run_dir(run_dir)
    try:
        async def _worker(i: int) -> None:
            await asyncio.sleep(0)
            write_auxiliary_compaction_triplet(
                source="web_extract",
                subject=f"https://example.com/{i}",
                raw_text=f"raw-{i}",
                compacted_text=f"summary-{i}",
                model="test-model",
            )

        async def _run_all():
            await asyncio.gather(*[_worker(i) for i in range(4)])

        asyncio.run(_run_all())
    finally:
        unbind_run_dir(tok_dir, tok_seq)

    pre_files = sorted(run_dir.glob("*_step_aux-web_extract_pre_compaction.json"))
    round_files = sorted(run_dir.glob("*_step_aux-web_extract_compaction_round_trip.json"))
    post_files = sorted(run_dir.glob("*_step_aux-web_extract_post_compaction.json"))

    assert len(pre_files) == 4
    assert len(round_files) == 4
    assert len(post_files) == 4


def test_write_compaction_triplet_creates_three_files(tmp_path):
    write_compaction_triplet(
        run_dir=tmp_path,
        idx=1,
        step_n=5,
        pre_messages=[{"role": "user", "content": "hi"}],
        summary_text="summary",
        post_messages=[{"role": "user", "content": "compressed"}],
    )
    names = {f.name for f in tmp_path.glob("*.json")}
    assert any("pre_compaction" in n for n in names)
    assert any("round_trip" in n for n in names)
    assert any("post_compaction" in n for n in names)


def test_rename_last_post_compaction_force_finish(tmp_path):
    write_compaction_triplet(
        run_dir=tmp_path,
        idx=1,
        step_n=5,
        pre_messages=[],
        summary_text="",
        post_messages=[],
    )
    rename_last_post_compaction_force_finish(tmp_path, 1)
    force_files = list(tmp_path.glob("*force_finish*"))
    assert len(force_files) == 1
