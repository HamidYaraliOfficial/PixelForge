"""
PixelForge - Quality Metrics & Quality Guardian
================================================

Real perceptual-quality measurement (SSIM / MS-SSIM / PSNR) used to:
  1. score benchmark candidates against each other (compression/candidates.py)
  2. let the Quality Guardian verify the FINAL output against the original and
     automatically retry with safer parameters if quality dropped too far.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
from PIL import Image
from skimage.metrics import structural_similarity as sk_ssim
from skimage.metrics import peak_signal_noise_ratio as sk_psnr


@dataclass
class QualityMetrics:
    ssim: float
    ms_ssim: float
    psnr: float
    estimated_quality: float  # single 0-100 blended score shown to the user


def _as_rgb_array(img: Image.Image, size: Optional[tuple] = None) -> np.ndarray:
    work = img.convert("RGB")
    if size and work.size != size:
        work = work.resize(size, Image.BICUBIC)
    return np.asarray(work, dtype=np.uint8)


def compute_metrics(original_path: str, candidate_path: str) -> QualityMetrics:
    with Image.open(original_path) as o, Image.open(candidate_path) as c:
        a = _as_rgb_array(o)
        b = _as_rgb_array(c, size=(a.shape[1], a.shape[0]))

    ssim_val = float(sk_ssim(a, b, channel_axis=2, data_range=255))
    ms_ssim_val = _multiscale_ssim(a, b)
    with np.errstate(divide="ignore"):
        try:
            raw_psnr = sk_psnr(a, b, data_range=255)
            psnr_val = 99.0 if not np.isfinite(raw_psnr) else float(raw_psnr)
        except Exception:
            psnr_val = 99.0  # identical images

    # Blend into a single human-friendly 0-100 "estimated quality" score.
    psnr_component = min(1.0, psnr_val / 50.0)
    estimated = 100.0 * (0.6 * ssim_val + 0.25 * ms_ssim_val + 0.15 * psnr_component)

    return QualityMetrics(
        ssim=round(ssim_val, 5),
        ms_ssim=round(ms_ssim_val, 5),
        psnr=round(psnr_val, 3),
        estimated_quality=round(max(0.0, min(100.0, estimated)), 2),
    )


def _multiscale_ssim(a: np.ndarray, b: np.ndarray, scales: int = 3) -> float:
    """A light-weight multi-scale SSIM: average SSIM across `scales` pyramid levels."""
    vals = []
    cur_a, cur_b = a, b
    for i in range(scales):
        if min(cur_a.shape[:2]) < 16:
            break
        vals.append(float(sk_ssim(cur_a, cur_b, channel_axis=2, data_range=255)))
        cur_a = cur_a[::2, ::2, :]
        cur_b = cur_b[::2, ::2, :]
    return float(np.mean(vals)) if vals else vals and vals[0] or 0.0


@dataclass
class GuardianVerdict:
    passed: bool
    metrics: QualityMetrics
    message: str


class QualityGuardian:
    """Re-checks a finished compression job and forces a safer retry if the
    perceptual quality drop exceeds the caller's threshold."""

    def __init__(self, min_ssim: float = 0.92, min_estimated_quality: float = 70.0):
        self.min_ssim = min_ssim
        self.min_estimated_quality = min_estimated_quality

    def evaluate(self, original_path: str, candidate_path: str) -> GuardianVerdict:
        m = compute_metrics(original_path, candidate_path)
        if m.ssim < self.min_ssim or m.estimated_quality < self.min_estimated_quality:
            return GuardianVerdict(
                passed=False, metrics=m,
                message=(f"Quality below threshold (SSIM {m.ssim:.3f} < {self.min_ssim} "
                          f"or score {m.estimated_quality:.1f} < {self.min_estimated_quality}). "
                          f"Retrying with safer parameters."),
            )
        return GuardianVerdict(passed=True, metrics=m, message="Quality accepted.")
