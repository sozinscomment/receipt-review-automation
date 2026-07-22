# LOGIC HEADER
# Input:          Nothing external — uses an in-memory/temp SQLite db per test.
# Transformation: Exercise Storage's CRUD paths directly.
# Output:         Pass/fail assertions.

import tempfile
from pathlib import Path

import pytest

from api.storage import FlaggedItem, Run, Storage


@pytest.fixture
def storage(tmp_path):
    return Storage(db_path=tmp_path / "test.db")


def test_create_and_list_run(storage):
    run = storage.create_run(Run(started_at="2026-01-01T00:00:00Z", files_processed=5))
    assert run.id is not None
    runs = storage.list_runs()
    assert len(runs) == 1
    assert runs[0].files_processed == 5


def test_runs_ordered_most_recent_first(storage):
    storage.create_run(Run(started_at="2026-01-01T00:00:00Z"))
    second = storage.create_run(Run(started_at="2026-01-02T00:00:00Z"))
    runs = storage.list_runs()
    assert runs[0].id == second.id


def test_create_and_list_flagged_item(storage):
    run = storage.create_run(Run(started_at="2026-01-01T00:00:00Z"))
    item = storage.create_flagged_item(FlaggedItem(
        run_id=run.id, source_file="r1.png", reason="extraction_failed",
        created_at="2026-01-01T00:00:00Z",
    ))
    assert item.id is not None
    items = storage.list_flagged_items()
    assert len(items) == 1
    assert items[0].reviewed is False


def test_mark_reviewed(storage):
    run = storage.create_run(Run(started_at="2026-01-01T00:00:00Z"))
    item = storage.create_flagged_item(FlaggedItem(
        run_id=run.id, source_file="r1.png", reason="duplicate_of: r0.png",
        created_at="2026-01-01T00:00:00Z",
    ))
    assert storage.mark_reviewed(item.id) is True
    fetched = storage.get_flagged_item(item.id)
    assert fetched.reviewed is True


def test_mark_reviewed_unknown_id_returns_false(storage):
    assert storage.mark_reviewed(9999) is False


def test_only_unreviewed_filter(storage):
    run = storage.create_run(Run(started_at="2026-01-01T00:00:00Z"))
    a = storage.create_flagged_item(FlaggedItem(
        run_id=run.id, source_file="a.png", reason="extraction_failed",
        created_at="2026-01-01T00:00:00Z",
    ))
    storage.create_flagged_item(FlaggedItem(
        run_id=run.id, source_file="b.png", reason="extraction_failed",
        created_at="2026-01-01T00:00:00Z",
    ))
    storage.mark_reviewed(a.id)
    unreviewed = storage.list_flagged_items(only_unreviewed=True)
    assert len(unreviewed) == 1
    assert unreviewed[0].source_file == "b.png"
