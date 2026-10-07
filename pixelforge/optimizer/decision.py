"""
PixelForge - Compression Decision Engine
=========================================

This is the "brain" of PixelForge. Given the features extracted by
``analysis/features.py`` and the user's stated goal, it produces a ranked list
of *candidate* (format, params) configurations worth actually encoding and
benchmarking (see ``compression/candidates.py``), plus a human-readable
explanation of *why* - shown to the user in Automatic Mode.

The engine intentionally never decides purely on file size: it also reasons
about perceptual quality expectations, alpha/transparency support, whether the
content is text/UI (which lossy DCT blur hurts badly) versus a photograph, and
whether re-encoding an already-lossy JPEG is even worth doing.

This is a transparent, rule-weighted heuristic system - not a black box. Every
decision appends a plain-language reason string so Automatic Mode can show its
work.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from analysis.features import ImageFeatures
from imgcodecs import available_codecs


class Goal(str, Enum):
    MAX_COMPRESSION = "max_compression"
    BALANCED = "balanced"
    MAX_QUALITY = "max_quality"
    TARGET_SIZE = "target_size"
    TARGET_PERCENTAGE = "target_percentage"
    WEB_OPTIMIZED = "web_optimized"


@dataclass
class Candidate:
    format: str
    params: dict
    priority: int = 0  # lower = tried first / preferred tie-break


@dataclass
class DecisionResult:
    candidates: list[Candidate]
    reasons: list[str] = field(default_factory=list)
    skip_reencode: bool = False  # true => just optimise/strip metadata, don't change codec
    suggested_max_dimension: Optional[int] = None


_GOAL_QUALITY_RANGE = {
    Goal.MAX_COMPRESSION: (35, 55),
    Goal.BALANCED: (65, 82),
    Goal.MAX_QUALITY: (90, 97),
    Goal.WEB_OPTIMIZED: (68, 80),
    Goal.TARGET_SIZE: (40, 90),        # will be overridden by binary search
    Goal.TARGET_PERCENTAGE: (40, 90),  # will be overridden by binary search
}


def decide(features: ImageFeatures, goal: Goal = Goal.BALANCED) -> DecisionResult:
    reasons: list[str] = []
    codecs = available_codecs()
    qlo, qhi = _GOAL_QUALITY_RANGE[goal]
    mid_q = (qlo + qhi) // 2
    candidates: list[Candidate] = []
    suggested_max_dim = None

    # ------------------------------------------------------------------
    # 1) Already-lossy JPEG re-encode sanity check
    # ------------------------------------------------------------------
    skip_reencode = False
    if features.already_lossy and features.format == "JPEG" and goal in (Goal.BALANCED, Goal.WEB_OPTIMIZED):
        skip_reencode = True
        reasons.append(
            "Source is already a JPEG; re-encoding its DCT coefficients again would add "
            "generational quality loss for little size benefit. PixelForge will instead "
            "apply a lossless Huffman re-optimisation and metadata cleanup."
        )
        candidates.append(Candidate("JPEG_LOSSLESS_REOPT", {}, priority=-1))
        return DecisionResult(candidates, reasons, skip_reencode=True)

    # ------------------------------------------------------------------
    # 2) Transparency requirement
    # ------------------------------------------------------------------
    if features.has_alpha:
        reasons.append("Image has an alpha channel, so JPEG (no transparency support) is excluded.")
        if codecs["AVIF"]:
            candidates.append(Candidate("AVIF", dict(quality=mid_q, speed=6), priority=0))
            reasons.append("AVIF offers the best size/quality ratio for transparent images when available.")
        if codecs["JXL"]:
            candidates.append(Candidate("JXL", dict(lossless=False, distance=_q_to_jxl_distance(mid_q), effort=7), priority=1))
        candidates.append(Candidate("WEBP", dict(quality=mid_q, method=6, lossless=goal == Goal.MAX_QUALITY), priority=2))
        candidates.append(Candidate("PNG", dict(compress_level=9, optimize=True), priority=3))
        reasons.append("PNG kept as a lossless fallback for maximum compatibility.")

    # ------------------------------------------------------------------
    # 3) Screenshot / UI / text-heavy content -> avoid DCT blur
    # ------------------------------------------------------------------
    elif features.screenshot_score > 0.55 or features.text_density > 0.5:
        reasons.append(
            f"Content looks like a screenshot or text/UI image (screenshot_score="
            f"{features.screenshot_score:.2f}, text_density={features.text_density:.2f}); "
            "lossy DCT-based codecs would blur text edges, so a lossless/near-lossless "
            "path is preferred."
        )
        if goal == Goal.MAX_COMPRESSION and codecs["WEBP"]:
            candidates.append(Candidate("WEBP", dict(quality=90, method=6, near_lossless=40), priority=0))
        else:
            candidates.append(Candidate("PNG", dict(compress_level=9, optimize=True, palette=features.approx_unique_colors < 256), priority=0))
            if codecs["WEBP"]:
                candidates.append(Candidate("WEBP", dict(quality=95, method=6, lossless=True), priority=1))

    # ------------------------------------------------------------------
    # 4) Illustration / icon / limited palette
    # ------------------------------------------------------------------
    elif features.illustration_score > 0.55 or features.approx_unique_colors < 256:
        reasons.append(
            f"Limited colour palette detected ({features.approx_unique_colors} approx. colours); "
            "palette-based PNG or lossless WebP compresses this far better than JPEG."
        )
        candidates.append(Candidate("PNG", dict(compress_level=9, optimize=True, palette=True), priority=0))
        if codecs["WEBP"]:
            candidates.append(Candidate("WEBP", dict(quality=95, method=6, lossless=True), priority=1))

    # ------------------------------------------------------------------
    # 5) Line art / black & white
    # ------------------------------------------------------------------
    elif features.line_art_score > 0.5:
        reasons.append("Line-art / black-and-white content detected; using a 1-bit/palette-friendly PNG.")
        candidates.append(Candidate("PNG", dict(compress_level=9, optimize=True, palette=True), priority=0))

    # ------------------------------------------------------------------
    # 6) General photograph
    # ------------------------------------------------------------------
    else:
        reasons.append(
            f"Photographic content detected (photo_score={features.photo_score:.2f}, "
            f"noise={features.noise_level:.2f}); a modern lossy codec gives the best "
            "size reduction with acceptable perceptual loss."
        )
        if codecs["AVIF"] and goal != Goal.MAX_QUALITY:
            candidates.append(Candidate("AVIF", dict(quality=mid_q, speed=6), priority=0))
            reasons.append("AVIF chosen as primary candidate: typically 30-50% smaller than JPEG at equal SSIM.")
        subsampling = 2 if goal in (Goal.MAX_COMPRESSION, Goal.WEB_OPTIMIZED) else (1 if goal == Goal.BALANCED else 0)
        candidates.append(Candidate("JPEG", dict(quality=mid_q, optimize=True, progressive=True,
                                                  subsampling=subsampling), priority=1))
        if codecs["WEBP"]:
            candidates.append(Candidate("WEBP", dict(quality=mid_q, method=6), priority=2))
        if codecs["JXL"] and goal == Goal.MAX_QUALITY:
            candidates.append(Candidate("JXL", dict(lossless=False, distance=0.5, effort=8), priority=0))
            reasons.append("Maximum-quality goal: JPEG XL at a low distance is included for near-lossless results.")

    # ------------------------------------------------------------------
    # Web-optimized goal: also cap dimensions (common web practice)
    # ------------------------------------------------------------------
    if goal == Goal.WEB_OPTIMIZED and max(features.width, features.height) > 1920:
        suggested_max_dim = 1920
        reasons.append("Web-Optimized goal: capping the longest edge at 1920px, a common web display size.")

    if goal == Goal.MAX_QUALITY and not features.has_alpha and features.photo_score < 0.4:
        # non-photo content at max quality -> lossless is safest
        candidates.insert(0, Candidate("PNG", dict(compress_level=9, optimize=True), priority=-1))
        reasons.append("Maximum-Quality goal on non-photographic content: lossless PNG placed first.")

    candidates.sort(key=lambda c: c.priority)
    return DecisionResult(candidates=candidates, reasons=reasons, skip_reencode=skip_reencode,
                           suggested_max_dimension=suggested_max_dim)


def _q_to_jxl_distance(quality: int) -> float:
    """Rough mapping from a 0-100 'quality' feel to JPEG XL's butteraugli distance
    (0 = lossless, ~1.0 = visually near-lossless, higher = more loss)."""
    quality = max(1, min(100, quality))
    return round(max(0.1, (100 - quality) / 25.0), 2)
