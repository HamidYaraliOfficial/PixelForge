"""
PixelForge - Processing Pipeline
===================================

Wires every subsystem together for ONE image:

    decode -> analyze -> (preset/rules) -> decision -> candidate benchmark
    -> quality guardian -> metadata policy -> resize (if requested) -> save
    -> compression report

This is intentionally a plain function-based orchestrator (not a class) so it
is trivial to call identically from the CLI, the GUI worker threads, and the
batch queue.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field, asdict
from typing import Optional

from PIL import Image

from analysis import analyze_image
from analysis.features import ImageFeatures
from imgcodecs import safe_open, ENCODERS, CorruptImageError, lossless_jpeg_reoptimize
from optimizer import decide, Goal, get_preset
from optimizer.rules import Rule, try_formats_override
from compression import run_benchmark, pick_best, AutoMode, resize_image, suggest_filter
from compression.target_size import compress_to_target_size, compress_to_target_percentage
from quality.metrics import QualityGuardian, compute_metrics
from metadata import apply_metadata_policy


@dataclass
class PipelineOptions:
    goal: Goal = Goal.BALANCED
    auto_mode: AutoMode = AutoMode.BALANCED
    preset: Optional[str] = None
    target_size_bytes: Optional[int] = None
    target_percentage: Optional[float] = None
    forced_format: Optional[str] = None          # Expert Mode: skip decision engine
    forced_params: Optional[dict] = None
    max_width: Optional[int] = None
    max_height: Optional[int] = None
    max_megapixels: Optional[float] = None
    resize_filter: Optional[str] = None
    metadata_policy: str = "keep_selected"
    privacy_mode: bool = False
    min_ssim: float = 0.90
    min_estimated_quality: float = 65.0
    output_dir: Optional[str] = None
    output_path: Optional[str] = None
    rules: list[Rule] = field(default_factory=list)


@dataclass
class CompressionReport:
    original_path: str
    output_path: str
    original_size: int
    final_size: int
    saved_bytes: int
    reduction_percent: float
    original_format: str
    output_format: str
    algorithm: str
    quality_params: dict
    encoding_time: float
    estimated_quality: float
    ssim: float
    psnr: float
    reasons: list[str]
    candidates_tried: list[dict] = field(default_factory=list)
    features: dict = field(default_factory=dict)
    kept_original: bool = False
    warnings: list[str] = field(default_factory=list)


def _apply_preset(options: PipelineOptions) -> PipelineOptions:
    if not options.preset:
        return options
    p = get_preset(options.preset)
    if p is None:
        return options
    options.goal = p.goal
    options.max_width = options.max_width or p.max_width
    options.max_height = options.max_height or p.max_height
    options.max_megapixels = options.max_megapixels or p.max_megapixels
    options.metadata_policy = p.metadata_policy
    options.privacy_mode = options.privacy_mode or p.privacy_mode
    return options


def process_single(input_path: str, options: Optional[PipelineOptions] = None) -> CompressionReport:
    options = _apply_preset(options or PipelineOptions())
    t_start = time.time()
    warnings: list[str] = []

    try:
        img = safe_open(input_path)
    except CorruptImageError as exc:
        raise

    features: ImageFeatures = analyze_image(input_path, img)

    # Resize before compression if requested
    if options.max_width or options.max_height or options.max_megapixels:
        filt = options.resize_filter or suggest_filter(features)
        img = resize_image(img, max_width=options.max_width, max_height=options.max_height,
                            max_megapixels=options.max_megapixels, filter_name=filt)

    out_dir = options.output_dir or os.path.dirname(os.path.abspath(input_path))
    os.makedirs(out_dir, exist_ok=True)
    base_name = os.path.splitext(os.path.basename(input_path))[0]

    # -------------------------------------------------------------------------
    # Expert Mode: user forced an exact format+params, skip the decision engine
    # -------------------------------------------------------------------------
    if options.forced_format:
        fmt = options.forced_format
        params = options.forced_params or {}
        out_path = options.output_path or os.path.join(out_dir, f"{base_name}.{fmt.lower()}")
        params.update(apply_metadata_policy(img, options.metadata_policy, privacy_mode=options.privacy_mode))
        result = ENCODERS[fmt](img, out_path, **{k: v for k, v in params.items() if k not in ("exif", "icc_profile")})
        m = compute_metrics(input_path, out_path)
        return _build_report(input_path, out_path, features, fmt, fmt, params, result.encode_time_s,
                              m, ["Expert Mode: user-specified format and parameters."], [], warnings)

    # -------------------------------------------------------------------------
    # Target size / target percentage mode
    # -------------------------------------------------------------------------
    if options.goal in (Goal.TARGET_SIZE, Goal.TARGET_PERCENTAGE):
        decision = decide(features, options.goal)
        fmt = decision.candidates[0].format if decision.candidates else "JPEG"
        if fmt not in ("JPEG", "WEBP", "AVIF"):
            fmt = "JPEG"
        out_path = options.output_path or os.path.join(out_dir, f"{base_name}_target.{fmt.lower()}")
        if options.goal == Goal.TARGET_SIZE and options.target_size_bytes:
            ts = compress_to_target_size(img, fmt, options.target_size_bytes, out_path=out_path)
        else:
            ts = compress_to_target_percentage(img, fmt, features.file_size,
                                                options.target_percentage or 50.0, out_path=out_path)
        m = compute_metrics(input_path, ts.out_path)
        reasons = decision.reasons + [
            f"Target search converged in {ts.iterations} iterations "
            f"({'within' if ts.achieved_within_tolerance else 'outside'} tolerance)."
        ]
        return _build_report(input_path, ts.out_path, features, fmt, fmt, ts.params, 0.0, m, reasons, [], warnings)

    # -------------------------------------------------------------------------
    # Automatic Mode: decision engine + benchmark + quality guardian
    # -------------------------------------------------------------------------
    decision = decide(features, options.goal)

    override_formats = try_formats_override(options.rules, features) if options.rules else None
    if override_formats:
        from optimizer.decision import Candidate
        decision.candidates = [c for c in decision.candidates if c.format in override_formats] or decision.candidates

    if decision.skip_reencode:
        out_path = options.output_path or os.path.join(out_dir, f"{base_name}_optimized.jpg")
        result = lossless_jpeg_reoptimize(input_path, out_path)
        m = compute_metrics(input_path, out_path)
        return _build_report(input_path, out_path, features, "JPEG", "JPEG", {"mode": "lossless_reoptimize"},
                              result.encode_time_s, m, decision.reasons, [], warnings)

    entries = run_benchmark(input_path, img, decision, mode=options.auto_mode)
    best = pick_best(entries, options.goal, target_size=options.target_size_bytes)
    if best is None:
        raise RuntimeError(f"No viable codec could encode {input_path} (all candidates failed or unavailable).")

    guardian = QualityGuardian(min_ssim=options.min_ssim, min_estimated_quality=options.min_estimated_quality)
    verdict = guardian.evaluate(input_path, best.out_path)
    retries = 0
    while not verdict.passed and retries < 2:
        warnings.append(verdict.message)
        safer = [e for e in entries if e is not best and e.metrics.estimated_quality > best.metrics.estimated_quality]
        if not safer:
            break
        best = max(safer, key=lambda e: e.metrics.estimated_quality)
        verdict = guardian.evaluate(input_path, best.out_path)
        retries += 1

    final_out_path = options.output_path or os.path.join(out_dir, f"{base_name}.{best.format.lower()}")
    if os.path.abspath(best.out_path) != os.path.abspath(final_out_path):
        os.makedirs(os.path.dirname(os.path.abspath(final_out_path)) or ".", exist_ok=True)
        with open(best.out_path, "rb") as src, open(final_out_path, "wb") as dst:
            dst.write(src.read())

    candidates_tried = [
        {"format": e.format, "params": e.params, "size_bytes": e.size_bytes,
         "encode_time_s": e.encode_time_s, "ssim": e.metrics.ssim, "psnr": e.metrics.psnr,
         "estimated_quality": e.metrics.estimated_quality, "score": e.score, "chosen": e is best}
        for e in entries
    ]

    return _build_report(input_path, final_out_path, features, features.format, best.format, best.params,
                          best.encode_time_s, best.metrics, decision.reasons, candidates_tried, warnings)


def _build_report(input_path, out_path, features, orig_fmt, out_fmt, params, enc_time, metrics,
                   reasons, candidates_tried, warnings) -> CompressionReport:
    original_size = features.file_size
    final_size = os.path.getsize(out_path)
    saved = original_size - final_size
    reduction = round(100.0 * saved / original_size, 2) if original_size else 0.0
    return CompressionReport(
        original_path=input_path, output_path=out_path, original_size=original_size,
        final_size=final_size, saved_bytes=saved, reduction_percent=reduction,
        original_format=orig_fmt, output_format=out_fmt, algorithm=out_fmt, quality_params=params,
        encoding_time=enc_time, estimated_quality=metrics.estimated_quality, ssim=metrics.ssim,
        psnr=metrics.psnr, reasons=reasons, candidates_tried=candidates_tried,
        features=asdict(features), warnings=warnings,
    )
