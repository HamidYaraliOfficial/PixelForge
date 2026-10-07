from database import Database


def test_schema_creates_all_tables(tmp_path):
    db = Database(str(tmp_path / "test.db"))
    tables = {r["name"] for r in db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    expected = {"jobs", "files", "analysis_results", "compression_runs", "candidates",
                "metrics", "presets", "rules", "settings", "history", "plugins",
                "schema_migrations"}
    assert expected.issubset(tables)
    db.close()


def test_job_file_run_lifecycle(tmp_path):
    db = Database(str(tmp_path / "test.db"))
    job_id = db.create_job("single", goal="balanced", total_files=1)
    file_id = db.add_file(job_id, "/tmp/x.png")
    db.save_analysis(file_id, {"width": 10, "height": 10})
    run_id = db.save_run(file_id, {
        "original_format": "PNG", "output_format": "WEBP", "algorithm": "WEBP",
        "original_size": 100, "final_size": 50, "saved_bytes": 50, "reduction_percent": 50.0,
        "encoding_time": 0.1, "estimated_quality": 95.0, "ssim": 0.98, "psnr": 40.0,
        "reasons": ["test"], "original_path": "/tmp/x.png", "output_path": "/tmp/x.webp",
    })
    db.update_file_status(file_id, "done", output_path="/tmp/x.webp")
    db.finish_job(job_id)
    assert run_id > 0
    summary = db.dashboard_summary()
    assert summary["files"] == 1
    assert summary["saved_bytes"] == 50
    db.close()


def test_wal_mode_enabled(tmp_path):
    db = Database(str(tmp_path / "test.db"))
    mode = db.conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"
    db.close()
