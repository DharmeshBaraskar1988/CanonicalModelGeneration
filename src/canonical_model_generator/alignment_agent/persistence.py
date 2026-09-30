"""SQLite persistence for Alignment Agent checkpoints and review drafts."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver


@contextmanager
def alignment_checkpointer(database: Path) -> Iterator[SqliteSaver]:
    """Open a strict, local LangGraph SQLite checkpointer."""
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database, check_same_thread=False)
    try:
        saver = SqliteSaver(
            connection,
            serde=JsonPlusSerializer(allowed_msgpack_modules=[]),
        )
        yield saver
    finally:
        connection.close()


def save_review_draft(database: Path, run_id: str, decisions: dict[str, Any]) -> None:
    """Upsert reviewer decisions separately from immutable graph checkpoints."""
    database.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS alignment_review_drafts (
                run_id TEXT PRIMARY KEY,
                decisions_json TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            INSERT INTO alignment_review_drafts(run_id, decisions_json, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(run_id) DO UPDATE SET
                decisions_json = excluded.decisions_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (run_id, json.dumps(decisions, sort_keys=True, separators=(",", ":"))),
        )


def load_review_draft(database: Path, run_id: str) -> dict[str, Any] | None:
    """Load persisted reviewer decisions for a run when present."""
    if not database.is_file():
        return None
    with sqlite3.connect(database) as connection:
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            ("alignment_review_drafts",),
        ).fetchone()
        if table is None:
            return None
        row = connection.execute(
            "SELECT decisions_json FROM alignment_review_drafts WHERE run_id = ?",
            (run_id,),
        ).fetchone()
    return json.loads(row[0]) if row else None
