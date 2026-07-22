# LOGIC HEADER
# Input:          A SQLite database path, plus run/flagged-item records produced by the
#                 pipeline wrapper (api/processor.py).
# Transformation: Persist one row per processing run and one row per flagged receipt
#                 (extraction failure, duplicate, or low-confidence result) so the
#                 dashboard and n8n workflow can query "what happened" and "what needs
#                 review" without re-reading spreadsheets or terminal output.
# Output:         CRUD functions: init_db, create_run, list_runs, create_flagged_item,
#                 list_flagged_items, mark_reviewed, get_flagged_item.

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

DEFAULT_DB_PATH = Path("data/review_automation.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    files_processed INTEGER NOT NULL DEFAULT 0,
    flagged_count INTEGER NOT NULL DEFAULT 0,
    duplicate_count INTEGER NOT NULL DEFAULT 0,
    engine TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS flagged_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    source_file TEXT NOT NULL,
    vendor TEXT,
    date TEXT,
    total REAL,
    reason TEXT NOT NULL,
    reviewed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs (id)
);
"""


@dataclass
class Run:
    started_at: str
    files_processed: int = 0
    flagged_count: int = 0
    duplicate_count: int = 0
    engine: str = ""
    id: Optional[int] = None


@dataclass
class FlaggedItem:
    run_id: int
    source_file: str
    reason: str
    created_at: str
    vendor: Optional[str] = None
    date: Optional[str] = None
    total: Optional[float] = None
    reviewed: bool = False
    id: Optional[int] = None


class Storage:
    """Thin SQLite wrapper. One instance per db_path; safe to reuse across requests
    since each call opens and closes its own connection (SQLite handles this fine
    at the traffic levels this project targets)."""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript(_SCHEMA)

    # --- runs ---

    def create_run(self, run: Run) -> Run:
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO runs (started_at, files_processed, flagged_count, "
                "duplicate_count, engine) VALUES (?, ?, ?, ?, ?)",
                (run.started_at, run.files_processed, run.flagged_count,
                 run.duplicate_count, run.engine),
            )
            run.id = cur.lastrowid
        return run

    def list_runs(self, limit: int = 50) -> list[Run]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [Run(**{k: row[k] for k in row.keys()}) for row in rows]

    # --- flagged items ---

    def create_flagged_item(self, item: FlaggedItem) -> FlaggedItem:
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO flagged_items (run_id, source_file, vendor, date, total, "
                "reason, reviewed, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (item.run_id, item.source_file, item.vendor, item.date, item.total,
                 item.reason, int(item.reviewed), item.created_at),
            )
            item.id = cur.lastrowid
        return item

    def list_flagged_items(self, only_unreviewed: bool = False) -> list[FlaggedItem]:
        query = "SELECT * FROM flagged_items"
        if only_unreviewed:
            query += " WHERE reviewed = 0"
        query += " ORDER BY id DESC"
        with self._conn() as conn:
            rows = conn.execute(query).fetchall()
        items = []
        for row in rows:
            d = {k: row[k] for k in row.keys()}
            d["reviewed"] = bool(d["reviewed"])
            items.append(FlaggedItem(**d))
        return items

    def get_flagged_item(self, item_id: int) -> Optional[FlaggedItem]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM flagged_items WHERE id = ?", (item_id,)
            ).fetchone()
        if row is None:
            return None
        d = {k: row[k] for k in row.keys()}
        d["reviewed"] = bool(d["reviewed"])
        return FlaggedItem(**d)

    def mark_reviewed(self, item_id: int) -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE flagged_items SET reviewed = 1 WHERE id = ?", (item_id,)
            )
        return cur.rowcount > 0
