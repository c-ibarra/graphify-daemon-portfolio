"""BatchConsumer single-reconstruction-per-batch guarantee.

See specs/vault-compiler/spec.md "Single reconstruction per batch".
"""

from __future__ import annotations

from pathlib import Path

from graphify_daemon.vault_compiler.batching import Batch, BatchConsumer, ChangeKind, FileChange


def test_fifty_file_batch_triggers_exactly_one_compile_call() -> None:
    call_count = 0

    def compile_batch(batch: Batch) -> None:
        nonlocal call_count
        call_count += 1

    changes = tuple(FileChange(path=Path(f"note-{i}.md"), kind=ChangeKind.MODIFIED) for i in range(50))
    batch = Batch(changes=changes)

    consumer = BatchConsumer(compile_batch)
    consumer.consume(batch)

    assert call_count == 1
