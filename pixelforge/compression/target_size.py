"""
PixelForge - Target Size / Target Percentage Compression
===========================================================

Implements a real binary search over the quality parameter of a
quality-controllable codec (JPEG / WebP / AVIF / JPEG XL-via-distance) to
converge on a user-specified target file size, or a target percentage
reduction relative to the original.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from typing import Optional

from PIL import Image

from imgcodecs import ENCODERS, CodecUnavailable

_QUALITY_CONTROLLABLE = {"JPEG", "WEBP", "AVIF"}


@dataclass
class TargetSizeResult:
    format: str
    params: dict
    size_bytes: int
    out_path: str
    iterations: int
    achieved_within_tolerance: bool


def compress_to_target_size(image: Image.Image, fmt: str, target_bytes: int,
                             out_path: Optional[str] = None, tolerance: float = 0.05,
                             extra_params: Optional[dict] = None, max_iterations: int = 12) -> TargetSizeResult:
    if fmt not in _QUALITY_CONTROLLABLE:
        raise ValueError(f"{fmt} does not support quality-based target-size search.")
    encoder = ENCODERS[fmt]
    extra_params = extra_params or {}
    out_path = out_path or tempfile.mktemp(suffix=f".{fmt.lower()}")

    lo, hi = 1, 100
    best_path = None
    best_size = None
    best_params = None
    iterations = 0

    while lo <= hi and iterations < max_iterations:
        mid = (lo + hi) // 2
        params = dict(extra_params)
        params["quality"] = mid
        try:
            result = encoder(image, out_path, **params)
        except CodecUnavailable:
            raise
        iterations += 1
        size = result.size_bytes

        if best_size is None or abs(size - target_bytes) < abs(best_size - target_bytes):
            best_size = size
            best_path = out_path
            best_params = params

        if size > target_bytes:
            hi = mid - 1
        else:
            lo = mid + 1

        if abs(size - target_bytes) <= target_bytes * tolerance:
            break

    within = best_size is not None and abs(best_size - target_bytes) <= target_bytes * tolerance
    return TargetSizeResult(
        format=fmt, params=best_params or {}, size_bytes=best_size or 0,
        out_path=best_path or out_path, iterations=iterations,
        achieved_within_tolerance=within,
    )


def compress_to_target_percentage(image: Image.Image, fmt: str, original_size: int,
                                   reduction_percent: float, **kwargs) -> TargetSizeResult:
    target_bytes = int(original_size * (1 - reduction_percent / 100.0))
    return compress_to_target_size(image, fmt, max(1, target_bytes), **kwargs)
