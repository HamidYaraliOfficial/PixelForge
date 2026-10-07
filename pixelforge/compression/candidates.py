"""
PixelForge - Auto Compression Benchmark Engine
=================================================

Turns the Decision Engine's candidate list into REAL encoded files, measures
real size / time / SSIM / PSNR for each, and picks the winner according to a
multi-criteria objective (size, perceptual quality, encode time, target
constraints) rather than "just pick the smallest file".

Auto modes:
  * FAST     - encode only the top 2 candidates, skip MS-SSIM (cheaper PSNR/SSIM only)
  * BALANCED - encode up to 4 candidates with full metrics
  * DEEP     - encode every candidate the decision engine proposed, at multiple
               quality steps each, for the most thorough Pareto search
"""

from __future__ import annotations

import os
import tempfile
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from PIL import Image

from imgcodecs import ENCODERS, EncodeResult, CodecUnavailable
from optimizer.decision import Candidate, DecisionResult, Goal
from quality.metrics import compute_metrics, QualityMetrics


class AutoMode(str, Enum):
    FAST = "fast"
    BALANCED = "balanced"
    DEEP = "deep"


_MODE_LIMITS = {AutoMode.FAST: 2, AutoMode.BALANCED: 4, AutoMode.DEEP: 999}
_MODE_TIME_BUDGET_S = {AutoMode.FAST: 5.0, AutoMode.BALANCED: 20.0, AutoMode.DEEP: 120.0}


@dataclass
class BenchmarkEntry:
    format: str
    params: dict
    size_bytes: int
    encode_time_s: float
    metrics: QualityMetrics
    out_path: str
    score: float = 0.0


def _quality_sweep(candidate: Candidate, mode: AutoMode) -> list[dict]:
    """For DEEP mode, try a couple of extra quality steps around the chosen value
    so the Pareto search actually has multiple points per format."""
    base = dict(candidate.params)
    if mode != AutoMode.DEEP or "quality" not in base:
        return [base]
    q = base["quality"]
    variants = []
    for delta in (-15, 0, 15):
        v = dict(base)
        v["quality"] = max(1, min(100, q + delta))
        variants.append(v)
    return variants


def run_benchmark(original_path: str, image: Image.Image, decision: DecisionResult,
                   mode: AutoMode = AutoMode.BALANCED, work_dir: Optional[str] = None) -> list[BenchmarkEntry]:
    work_dir = work_dir or tempfile.mkdtemp(prefix="pixelforge_bench_")
    os.makedirs(work_dir, exist_ok=True)

    limit = _MODE_LIMITS[mode]
    time_budget = _MODE_TIME_BUDGET_S[mode]
    entries: list[BenchmarkEntry] = []
    started = time.time()

    tried = 0
    for cand in decision.candidates:
        if tried >= limit or (time.time() - started) > time_budget:
            break
        encoder = ENCODERS.get(cand.format)
        if encoder is None:
            continue
        for params in _quality_sweep(cand, mode):
            ext = cand.format.lower()
            out_path = os.path.join(work_dir, f"candidate_{tried}_{cand.format}.{ext}")
            try:
                result: EncodeResult = encoder(image, out_path, **params)
            except CodecUnavailable:
                continue
            except Exception:
                continue
            try:
                m = compute_metrics(original_path, out_path)
            except Exception:
                continue
            entries.append(BenchmarkEntry(
                format=cand.format, params=params, size_bytes=result.size_bytes,
                encode_time_s=result.encode_time_s, metrics=m, out_path=out_path,
            ))
            tried += 1
            if tried >= limit or (time.time() - started) > time_budget:
                break

    _score_entries(entries, goal=Goal.BALANCED)
    return entries


def _score_entries(entries: list[BenchmarkEntry], goal: Goal) -> None:
    if not entries:
        return
    max_size = max(e.size_bytes for e in entries) or 1
    max_time = max(e.encode_time_s for e in entries) or 1e-6

    # weights per goal: (size_weight, quality_weight, time_weight)
    weights = {
        Goal.MAX_COMPRESSION: (0.7, 0.25, 0.05),
        Goal.BALANCED: (0.4, 0.5, 0.1),
        Goal.MAX_QUALITY: (0.1, 0.85, 0.05),
        Goal.WEB_OPTIMIZED: (0.55, 0.4, 0.05),
        Goal.TARGET_SIZE: (0.6, 0.35, 0.05),
        Goal.TARGET_PERCENTAGE: (0.6, 0.35, 0.05),
    }.get(goal, (0.4, 0.5, 0.1))

    for e in entries:
        size_score = 1.0 - (e.size_bytes / max_size)          # smaller is better
        quality_score = e.metrics.estimated_quality / 100.0   # higher is better
        time_score = 1.0 - (e.encode_time_s / max_time)       # faster is better
        e.score = round(weights[0] * size_score + weights[1] * quality_score + weights[2] * time_score, 5)


def pick_best(entries: list[BenchmarkEntry], goal: Goal = Goal.BALANCED,
              target_size: Optional[int] = None) -> Optional[BenchmarkEntry]:
    if not entries:
        return None
    _score_entries(entries, goal)
    if target_size:
        under = [e for e in entries if e.size_bytes <= target_size]
        pool = under if under else entries
        # among those under target, maximise quality; otherwise get closest to target
        if under:
            return max(pool, key=lambda e: e.metrics.estimated_quality)
        return min(pool, key=lambda e: abs(e.size_bytes - target_size))
    return max(entries, key=lambda e: e.score)
