"""
PixelForge - Batch Processing Queue
======================================

A real thread-pool based job queue:
  * Parallel workers sized to the CPU core count (adaptive - never more workers
    than pending files).
  * Pause / Resume via a shared threading.Event.
  * Cancel of the whole batch or of an individual pending file.
  * Automatic retry (bounded) for transient failures.
  * Priority queue so urgent files can jump ahead.
  * Per-file error isolation: one corrupt/failing file is logged and skipped;
    it never stops the rest of the batch.
  * Crash recovery: progress is checkpointed to the SQLite database after every
    file, so a batch interrupted by a crash or restart can be resumed by
    reloading pending/failed files for the same job id.
  * Each file gets an INDEPENDENT decision-engine result - the queue never
    forces one format onto every image.
"""

from __future__ import annotations

import heapq
import itertools
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass, field
from typing import Callable, Optional

from database import Database
from optimizer.rules import Rule, post_process_gates, applicable_rules
from pipeline.pipeline import process_single, PipelineOptions, CompressionReport

logger = logging.getLogger("pixelforge.batch")


@dataclass(order=True)
class _QueueItem:
    priority: int
    seq: int
    path: str = field(compare=False)
    file_id: int = field(compare=False)


@dataclass
class BatchResult:
    file_id: int
    input_path: str
    report: Optional[CompressionReport]
    error: Optional[str] = None
    kept_original: bool = False


class BatchQueue:
    def __init__(self, db: Database, options: PipelineOptions, max_workers: Optional[int] = None,
                 max_retries: int = 2, rules: Optional[list[Rule]] = None,
                 on_progress: Optional[Callable[[BatchResult], None]] = None):
        self.db = db
        self.options = options
        self.max_workers = max_workers or max(1, os.cpu_count() or 4)
        self.max_retries = max_retries
        self.rules = rules or []
        self.on_progress = on_progress

        self._heap: list[_QueueItem] = []
        self._counter = itertools.count()
        self._lock = threading.Lock()
        self._pause_event = threading.Event()
        self._pause_event.set()  # not paused by default
        self._cancelled = set()
        self._cancel_all = threading.Event()
        self._retries: dict[int, int] = {}
        self.job_id: Optional[int] = None
        self._executor: Optional[ThreadPoolExecutor] = None
        self._futures: list[Future] = []

    # ---- queue management -----------------------------------------------------------

    def add_files(self, paths: list[str], priority: int = 0) -> int:
        if self.job_id is None:
            self.job_id = self.db.create_job("batch", goal=self.options.goal.value, total_files=len(paths))
        with self._lock:
            for p in paths:
                fid = self.db.add_file(self.job_id, p, priority=priority)
                heapq.heappush(self._heap, _QueueItem(priority, next(self._counter), p, fid))
        return self.job_id

    def resume_job(self, job_id: int) -> None:
        """Crash recovery: reload pending/failed files of a previous job."""
        self.job_id = job_id
        rows = self.db.conn.execute(
            "SELECT id, input_path, priority FROM files WHERE job_id=? AND status IN ('pending','failed','running')",
            (job_id,),
        ).fetchall()
        with self._lock:
            for r in rows:
                heapq.heappush(self._heap, _QueueItem(r["priority"], next(self._counter), r["input_path"], r["id"]))

    def pause(self) -> None:
        self._pause_event.clear()

    def resume(self) -> None:
        self._pause_event.set()

    def cancel_all(self) -> None:
        self._cancel_all.set()

    def cancel_file(self, file_id: int) -> None:
        self._cancelled.add(file_id)

    # ---- execution --------------------------------------------------------------------

    def run(self, blocking: bool = True) -> list[BatchResult]:
        results: list[BatchResult] = []
        n_workers = min(self.max_workers, max(1, len(self._heap)))
        self._executor = ThreadPoolExecutor(max_workers=n_workers, thread_name_prefix="pf-worker")

        def worker_loop():
            local_results = []
            while True:
                self._pause_event.wait()
                if self._cancel_all.is_set():
                    break
                with self._lock:
                    if not self._heap:
                        break
                    item = heapq.heappop(self._heap)
                if item.file_id in self._cancelled:
                    self.db.update_file_status(item.file_id, "skipped")
                    continue
                res = self._process_one(item)
                local_results.append(res)
                if self.on_progress:
                    try:
                        self.on_progress(res)
                    except Exception:
                        logger.exception("on_progress callback failed")
            return local_results

        futures = [self._executor.submit(worker_loop) for _ in range(n_workers)]
        if blocking:
            for fut in futures:
                results.extend(fut.result())
            self._executor.shutdown(wait=True)
            if self.job_id is not None:
                self.db.finish_job(self.job_id)
        else:
            self._futures = futures
        return results

    def _process_one(self, item: _QueueItem) -> BatchResult:
        self.db.update_file_status(item.file_id, "running")
        attempt = 0
        last_error = None
        while attempt <= self.max_retries:
            try:
                report = process_single(item.path, self.options)
                features_dict = report.features
                self.db.save_analysis(item.file_id, features_dict)

                keep_new = True
                if self.rules:
                    keep_new, gate_messages = post_process_gates(
                        self.rules, _DictFeatures(features_dict),
                        report.reduction_percent, report.ssim,
                    )
                    report.warnings.extend(gate_messages)

                if not keep_new:
                    report.kept_original = True
                    self.db.update_file_status(item.file_id, "skipped", output_path=item.path)
                else:
                    self.db.save_run(item.file_id, {
                        "original_format": report.original_format, "output_format": report.output_format,
                        "algorithm": report.algorithm, "quality_params": report.quality_params,
                        "original_size": report.original_size, "final_size": report.final_size,
                        "saved_bytes": report.saved_bytes, "reduction_percent": report.reduction_percent,
                        "encoding_time": report.encoding_time, "estimated_quality": report.estimated_quality,
                        "ssim": report.ssim, "psnr": report.psnr, "reasons": report.reasons,
                        "original_path": report.original_path, "output_path": report.output_path,
                    }, candidates=report.candidates_tried)
                    self.db.update_file_status(item.file_id, "done", output_path=report.output_path)
                return BatchResult(item.file_id, item.path, report, kept_original=not keep_new)
            except Exception as exc:
                last_error = str(exc)
                attempt += 1
                logger.warning("Attempt %d failed for %s: %s", attempt, item.path, exc)
                time.sleep(0.2)
        self.db.update_file_status(item.file_id, "failed", error_message=last_error)
        return BatchResult(item.file_id, item.path, None, error=last_error)

    def pending_count(self) -> int:
        with self._lock:
            return len(self._heap)


class _DictFeatures:
    """Adapter so rule matching can run against a plain dict pulled back from
    the database (e.g. on crash-recovery resume) as well as a live ImageFeatures."""
    def __init__(self, d: dict):
        self.__dict__.update(d)
