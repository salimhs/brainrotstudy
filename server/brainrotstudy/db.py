"""Tiny SQLite layer for job metadata.

No ORM on purpose — job rows are few, queries are trivial, stdlib sqlite3 is fast
and ships with Python. Thread-safe via ``check_same_thread=False`` plus a short
lock; concurrency is dominated by the pipeline, not the DB.
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from typing import Iterator

from .config import get_settings
from .schemas import JobOptions, JobStage, JobStatus, JobView, utc_now

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id           TEXT PRIMARY KEY,
    status       TEXT NOT NULL,
    stage        TEXT,
    progress     INTEGER NOT NULL DEFAULT 0,
    title        TEXT NOT NULL DEFAULT '',
    input_kind   TEXT NOT NULL,
    input_filename TEXT,
    options_json TEXT NOT NULL,
    error        TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC);
"""

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def _connect() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        db_path = get_settings().resolve_db()
        _conn = sqlite3.connect(db_path, check_same_thread=False, isolation_level=None)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA synchronous=NORMAL")
        _conn.executescript(_SCHEMA)
    return _conn


@contextmanager
def _cursor() -> Iterator[sqlite3.Cursor]:
    conn = _connect()
    with _lock:
        cur = conn.cursor()
        try:
            yield cur
        finally:
            cur.close()


def _row_to_view(row: sqlite3.Row) -> JobView:
    return JobView(
        id=row["id"],
        status=JobStatus(row["status"]),
        stage=JobStage(row["stage"]) if row["stage"] else None,
        progress=row["progress"],
        title=row["title"],
        input_kind=row["input_kind"],
        input_filename=row["input_filename"],
        error=row["error"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        options=JobOptions.model_validate_json(row["options_json"]),
        artifacts=None,
    )


def create_job(
    job_id: str,
    *,
    title: str,
    input_kind: str,
    input_filename: str | None,
    options: JobOptions,
) -> JobView:
    now = utc_now().isoformat()
    with _cursor() as cur:
        cur.execute(
            """
            INSERT INTO jobs (id, status, stage, progress, title, input_kind,
                              input_filename, options_json, created_at, updated_at)
            VALUES (?, ?, NULL, 0, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                JobStatus.QUEUED.value,
                title,
                input_kind,
                input_filename,
                options.model_dump_json(),
                now,
                now,
            ),
        )
    return get_job(job_id)  # type: ignore[return-value]


def get_job(job_id: str) -> JobView | None:
    with _cursor() as cur:
        row = cur.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return _row_to_view(row) if row else None


def list_jobs(limit: int = 50) -> list[JobView]:
    with _cursor() as cur:
        rows = cur.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_row_to_view(r) for r in rows]


def update_job(
    job_id: str,
    *,
    status: JobStatus | None = None,
    stage: JobStage | None = None,
    progress: int | None = None,
    title: str | None = None,
    error: str | None = None,
) -> JobView | None:
    fields: dict[str, str | int | None] = {}
    if status is not None:
        fields["status"] = status.value
    if stage is not None:
        fields["stage"] = stage.value
    if progress is not None:
        fields["progress"] = progress
    if title is not None:
        fields["title"] = title
    if error is not None:
        fields["error"] = error
    if not fields:
        return get_job(job_id)

    fields["updated_at"] = utc_now().isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values())
    values.append(job_id)

    with _cursor() as cur:
        cur.execute(f"UPDATE jobs SET {set_clause} WHERE id = ?", values)
    return get_job(job_id)


def delete_job(job_id: str) -> bool:
    with _cursor() as cur:
        cur.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        return cur.rowcount > 0


# -- test hook --------------------------------------------------------------

def _reset_for_tests() -> None:
    """Close the cached connection so tests can redirect the DB path."""
    global _conn
    if _conn is not None:
        _conn.close()
        _conn = None
