"""
PixelForge - Local Application Database (SQLite)
===================================================

Stores everything the GUI and CLI need to persist between runs: batch jobs,
per-file analysis and compression results, benchmarked candidates, presets,
custom rules, settings, revert-able history, and installed plugins.

Uses WAL mode for concurrent read/write safety between the GUI thread and
background worker threads, wraps writes in transactions, and keeps a simple
``schema_migrations`` table so future schema changes can be applied
incrementally instead of destroying user data.
"""

from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import time
from typing import Any, Iterator, Optional

SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,                 -- 'single' | 'batch'
    status TEXT NOT NULL DEFAULT 'pending',
    goal TEXT,
    created_at REAL NOT NULL,
    finished_at REAL,
    total_files INTEGER DEFAULT 0,
    completed_files INTEGER DEFAULT 0,
    failed_files INTEGER DEFAULT 0,
    total_original_bytes INTEGER DEFAULT 0,
    total_final_bytes INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER REFERENCES jobs(id) ON DELETE CASCADE,
    input_path TEXT NOT NULL,
    output_path TEXT,
    status TEXT NOT NULL DEFAULT 'pending',   -- pending|running|done|failed|skipped
    priority INTEGER DEFAULT 0,
    error_message TEXT,
    created_at REAL NOT NULL,
    updated_at REAL
);

CREATE TABLE IF NOT EXISTS analysis_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER REFERENCES files(id) ON DELETE CASCADE,
    features_json TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS compression_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER REFERENCES files(id) ON DELETE CASCADE,
    original_format TEXT,
    output_format TEXT,
    algorithm TEXT,
    encoder_params_json TEXT,
    original_size INTEGER,
    final_size INTEGER,
    saved_bytes INTEGER,
    reduction_percent REAL,
    encoding_time_s REAL,
    estimated_quality REAL,
    ssim REAL,
    psnr REAL,
    reasons_json TEXT,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER REFERENCES compression_runs(id) ON DELETE CASCADE,
    format TEXT,
    params_json TEXT,
    size_bytes INTEGER,
    encode_time_s REAL,
    ssim REAL,
    psnr REAL,
    estimated_quality REAL,
    score REAL,
    chosen INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER REFERENCES compression_runs(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    value REAL
);

CREATE TABLE IF NOT EXISTS presets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    config_json TEXT NOT NULL,
    is_builtin INTEGER DEFAULT 0,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    condition_json TEXT NOT NULL,
    action_json TEXT NOT NULL,
    enabled INTEGER DEFAULT 1,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER REFERENCES files(id) ON DELETE CASCADE,
    run_id INTEGER REFERENCES compression_runs(id) ON DELETE CASCADE,
    original_path TEXT,
    output_path TEXT,
    reverted INTEGER DEFAULT 0,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS plugins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    module_path TEXT NOT NULL,
    enabled INTEGER DEFAULT 1,
    registered_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_files_job ON files(job_id);
CREATE INDEX IF NOT EXISTS idx_runs_file ON compression_runs(file_id);
CREATE INDEX IF NOT EXISTS idx_candidates_run ON candidates(run_id);
CREATE INDEX IF NOT EXISTS idx_history_file ON history(file_id);
"""


class Database:
    def __init__(self, path: str = "pixelforge.db"):
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA foreign_keys=ON;")
        self.conn.row_factory = sqlite3.Row
        self.init_schema()

    def init_schema(self) -> None:
        with self.transaction():
            self.conn.executescript(SCHEMA_SQL)
            row = self.conn.execute("SELECT MAX(version) AS v FROM schema_migrations").fetchone()
            current = row["v"] if row and row["v"] is not None else 0
            if current < SCHEMA_VERSION:
                self.conn.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (SCHEMA_VERSION, time.time()),
                )

    @contextlib.contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        try:
            yield self.conn
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def backup(self, backup_path: str) -> None:
        dest = sqlite3.connect(backup_path)
        with dest:
            self.conn.backup(dest)
        dest.close()

    # ---- convenience helpers used by cli/gui/pipeline -----------------------------

    def create_job(self, kind: str, goal: Optional[str] = None, total_files: int = 0) -> int:
        with self.transaction():
            cur = self.conn.execute(
                "INSERT INTO jobs(kind, status, goal, created_at, total_files) VALUES (?, 'running', ?, ?, ?)",
                (kind, goal, time.time(), total_files),
            )
            return cur.lastrowid

    def finish_job(self, job_id: int) -> None:
        row = self.conn.execute(
            "SELECT COUNT(*) c, SUM(CASE WHEN status='done' THEN 1 ELSE 0 END) d, "
            "SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) f FROM files WHERE job_id=?",
            (job_id,),
        ).fetchone()
        with self.transaction():
            self.conn.execute(
                "UPDATE jobs SET status='completed', finished_at=?, completed_files=?, failed_files=? WHERE id=?",
                (time.time(), row["d"] or 0, row["f"] or 0, job_id),
            )

    def add_file(self, job_id: int, input_path: str, priority: int = 0) -> int:
        with self.transaction():
            cur = self.conn.execute(
                "INSERT INTO files(job_id, input_path, status, priority, created_at) "
                "VALUES (?, ?, 'pending', ?, ?)",
                (job_id, input_path, priority, time.time()),
            )
            return cur.lastrowid

    def update_file_status(self, file_id: int, status: str, output_path: Optional[str] = None,
                             error_message: Optional[str] = None) -> None:
        with self.transaction():
            self.conn.execute(
                "UPDATE files SET status=?, output_path=?, error_message=?, updated_at=? WHERE id=?",
                (status, output_path, error_message, time.time(), file_id),
            )

    def save_analysis(self, file_id: int, features_dict: dict) -> None:
        with self.transaction():
            self.conn.execute(
                "INSERT INTO analysis_results(file_id, features_json, created_at) VALUES (?, ?, ?)",
                (file_id, json.dumps(features_dict), time.time()),
            )

    def save_run(self, file_id: int, report: dict, candidates: Optional[list[dict]] = None) -> int:
        with self.transaction():
            cur = self.conn.execute(
                """INSERT INTO compression_runs
                   (file_id, original_format, output_format, algorithm, encoder_params_json,
                    original_size, final_size, saved_bytes, reduction_percent, encoding_time_s,
                    estimated_quality, ssim, psnr, reasons_json, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (file_id, report.get("original_format"), report.get("output_format"),
                 report.get("algorithm"), json.dumps(report.get("quality_params", {})),
                 report.get("original_size"), report.get("final_size"), report.get("saved_bytes"),
                 report.get("reduction_percent"), report.get("encoding_time"),
                 report.get("estimated_quality"), report.get("ssim"), report.get("psnr"),
                 json.dumps(report.get("reasons", [])), time.time()),
            )
            run_id = cur.lastrowid
            for c in candidates or []:
                self.conn.execute(
                    """INSERT INTO candidates(run_id, format, params_json, size_bytes, encode_time_s,
                       ssim, psnr, estimated_quality, score, chosen)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (run_id, c.get("format"), json.dumps(c.get("params", {})), c.get("size_bytes"),
                     c.get("encode_time_s"), c.get("ssim"), c.get("psnr"), c.get("estimated_quality"),
                     c.get("score"), int(c.get("chosen", False))),
                )
            self.conn.execute(
                "INSERT INTO history(file_id, run_id, original_path, output_path, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (file_id, run_id, report.get("original_path"), report.get("output_path"), time.time()),
            )
            return run_id

    def get_history(self, limit: int = 200) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM history ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()

    def dashboard_summary(self) -> dict:
        row = self.conn.execute(
            "SELECT COUNT(*) files, SUM(original_size) orig, SUM(final_size) fin, "
            "AVG(reduction_percent) avg_reduction, AVG(estimated_quality) avg_quality, "
            "SUM(encoding_time_s) total_time FROM compression_runs"
        ).fetchone()
        return {
            "files": row["files"] or 0,
            "original_bytes": row["orig"] or 0,
            "final_bytes": row["fin"] or 0,
            "saved_bytes": (row["orig"] or 0) - (row["fin"] or 0),
            "avg_reduction_percent": round(row["avg_reduction"] or 0, 2),
            "avg_estimated_quality": round(row["avg_quality"] or 0, 2),
            "total_processing_time_s": round(row["total_time"] or 0, 2),
        }

    def close(self) -> None:
        self.conn.close()
