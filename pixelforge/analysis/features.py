"""
PixelForge - Image Analysis Engine
===================================

This module inspects a decoded image and extracts a rich feature set that the
Compression Decision Engine (see ``optimizer/decision.py``) uses to choose the
best output format, codec and parameters for THAT specific image, instead of
applying one fixed setting to every file.

All numbers here are computed from real pixel data (via NumPy / Pillow) - there
is no placeholder or fake metric. Several signals (photo-vs-illustration,
screenshot-vs-photo, text-density, flat-region-ratio, noise-level) are
heuristic estimates rather than a trained classifier; this is documented
explicitly so nobody mistakes them for ground truth. They are combined in the
decision engine as *weighted evidence*, not hard rules.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field, asdict
from typing import Optional

import numpy as np
from PIL import Image, ImageFilter, ImageStat

MAX_SAFE_PIXELS = 300_000_000  # decompression-bomb guard, see codecs/registry.py


@dataclass
class ImageFeatures:
    # --- basic file / container info -------------------------------------------------
    path: str
    file_size: int
    format: str
    mime_type: str
    width: int
    height: int
    aspect_ratio: float
    megapixels: float

    # --- colour / bit-depth ------------------------------------------------------------
    mode: str
    color_space: str          # RGB / CMYK / GRAY / PALETTE
    has_alpha: bool
    is_grayscale: bool
    bit_depth: int
    approx_unique_colors: int
    palette_ratio: float      # unique_colors / total_pixels (small => flat / iconic)

    # --- statistical texture signals ---------------------------------------------------
    entropy: float
    contrast: float           # std-dev of luminance
    dynamic_range: float      # 1st-99th percentile luminance spread, normalised 0..1
    edge_density: float       # fraction of pixels that are strong edges
    sharpness: float          # variance of Laplacian-like high-pass response
    noise_level: float        # estimated sensor/compression noise (0..1)
    flat_region_ratio: float  # fraction of image that is near-flat blocks

    # --- heuristic content-type scores (0..1, higher = more likely) -------------------
    photo_score: float
    illustration_score: float
    screenshot_score: float
    text_density: float
    line_art_score: float

    # --- misc ----------------------------------------------------------------------
    dpi: tuple = (72, 72)
    already_lossy: bool = False
    exif_present: bool = False
    icc_present: bool = False


def _shannon_entropy(gray: np.ndarray) -> float:
    hist, _ = np.histogram(gray, bins=256, range=(0, 255))
    p = hist.astype(np.float64)
    p = p[p > 0] / gray.size
    return float(-(p * np.log2(p)).sum())


def _edge_density_and_sharpness(gray_img: Image.Image) -> tuple[float, float]:
    edges = gray_img.filter(ImageFilter.FIND_EDGES)
    arr = np.asarray(edges, dtype=np.float64)
    # sharpness ~ variance of the edge response (a cheap Laplacian-variance proxy)
    sharpness = float(arr.var())
    strong = (arr > 40).mean()
    return float(strong), sharpness


def _flat_region_ratio(gray: np.ndarray, block: int = 8, thresh: float = 4.0) -> float:
    h, w = gray.shape
    h2, w2 = (h // block) * block, (w // block) * block
    if h2 == 0 or w2 == 0:
        return 0.0
    cropped = gray[:h2, :w2].astype(np.float64)
    blocks = cropped.reshape(h2 // block, block, w2 // block, block).swapaxes(1, 2)
    stds = blocks.reshape(h2 // block, w2 // block, -1).std(axis=2)
    return float((stds < thresh).mean())


def _noise_estimate(gray_img: Image.Image) -> float:
    blurred = gray_img.filter(ImageFilter.GaussianBlur(radius=2))
    a = np.asarray(gray_img, dtype=np.float64)
    b = np.asarray(blurred, dtype=np.float64)
    residual = a - b
    # normalise: typical camera noise std is roughly in the 0-15 range
    return float(min(1.0, residual.std() / 20.0))


def _approx_unique_colors(img: Image.Image, cap: int = 100_000) -> int:
    small = img
    if img.width * img.height > 512 * 512:
        small = img.copy()
        small.thumbnail((512, 512))
    colors = small.convert("RGB").getcolors(maxcolors=cap)
    if colors is None:
        return cap
    return len(colors)


def analyze_image(path: str, pil_image: Optional[Image.Image] = None) -> ImageFeatures:
    """Run the full analysis pipeline on an image already on disk.

    Raises ``ValueError`` for images that exceed the safe pixel budget, so the
    caller can reject decompression-bomb style inputs before doing real work.
    """
    file_size = os.path.getsize(path)
    img = pil_image or Image.open(path)
    img_format = (img.format or "UNKNOWN").upper()

    if img.width * img.height > MAX_SAFE_PIXELS:
        raise ValueError(
            f"Image {path} has {img.width * img.height} pixels, "
            f"exceeding the safety limit of {MAX_SAFE_PIXELS}."
        )

    mode = img.mode
    has_alpha = mode in ("RGBA", "LA", "PA") or "transparency" in img.info
    is_grayscale = mode in ("L", "LA", "1", "I", "F")

    if mode == "CMYK":
        color_space = "CMYK"
    elif is_grayscale:
        color_space = "GRAY"
    elif mode == "P":
        color_space = "PALETTE"
    else:
        color_space = "RGB"

    bit_depth = {"1": 1, "L": 8, "P": 8, "RGB": 24, "RGBA": 32,
                 "I": 32, "F": 32, "CMYK": 32, "LA": 16}.get(mode, 24)

    rgb = img.convert("RGB")
    gray_img = img.convert("L")
    gray = np.asarray(gray_img, dtype=np.uint8)

    entropy = _shannon_entropy(gray)
    stat = ImageStat.Stat(gray_img)
    contrast = float(stat.stddev[0])

    p1, p99 = np.percentile(gray, [1, 99])
    dynamic_range = float((p99 - p1) / 255.0)

    edge_density, sharpness = _edge_density_and_sharpness(gray_img)
    flat_ratio = _flat_region_ratio(gray)
    noise = _noise_estimate(gray_img)
    unique_colors = _approx_unique_colors(rgb)
    total_px = img.width * img.height
    palette_ratio = unique_colors / max(1, total_px)

    # --- heuristic content classification -------------------------------------------
    # Photos: many colours, moderate-high noise/edge texture spread continuously.
    photo_score = _clamp(
        0.45 * _norm(unique_colors, 500, 20000)
        + 0.30 * _norm(noise, 0.03, 0.5)
        + 0.25 * (1.0 - flat_ratio)
    )
    # Illustrations / icons: few colours, large flat regions, crisp edges.
    illustration_score = _clamp(
        0.5 * (1.0 - _norm(unique_colors, 50, 5000))
        + 0.3 * flat_ratio
        + 0.2 * _norm(edge_density, 0.02, 0.25)
    )
    # Screenshots: very large flat regions + limited palette + sharp thin edges (UI/text).
    screenshot_score = _clamp(
        0.4 * flat_ratio
        + 0.3 * (1.0 - _norm(unique_colors, 50, 20000))
        + 0.3 * _norm(edge_density, 0.01, 0.15)
    )
    # crude text-density proxy: high edge density concentrated with high flatness elsewhere
    text_density = _clamp(0.6 * edge_density * 4 + 0.4 * flat_ratio) if flat_ratio > 0.4 else _clamp(edge_density * 2)
    line_art_score = _clamp(
        0.6 * (1.0 - _norm(unique_colors, 2, 64)) + 0.4 * flat_ratio
    ) if is_grayscale or unique_colors < 64 else 0.0

    already_lossy = img_format in ("JPEG", "JPG", "WEBP", "AVIF", "HEIC", "HEIF")
    exif_present = bool(getattr(img, "_getexif", None) and img._getexif())
    icc_present = "icc_profile" in img.info

    return ImageFeatures(
        path=path,
        file_size=file_size,
        format=img_format,
        mime_type=_mime_for(img_format),
        width=img.width,
        height=img.height,
        aspect_ratio=round(img.width / max(1, img.height), 4),
        megapixels=round(total_px / 1_000_000, 3),
        mode=mode,
        color_space=color_space,
        has_alpha=has_alpha,
        is_grayscale=is_grayscale,
        bit_depth=bit_depth,
        approx_unique_colors=unique_colors,
        palette_ratio=round(palette_ratio, 6),
        entropy=round(entropy, 4),
        contrast=round(contrast, 4),
        dynamic_range=round(dynamic_range, 4),
        edge_density=round(edge_density, 4),
        sharpness=round(sharpness, 4),
        noise_level=round(noise, 4),
        flat_region_ratio=round(flat_ratio, 4),
        photo_score=round(photo_score, 4),
        illustration_score=round(illustration_score, 4),
        screenshot_score=round(screenshot_score, 4),
        text_density=round(text_density, 4),
        line_art_score=round(line_art_score, 4),
        dpi=img.info.get("dpi", (72, 72)),
        already_lossy=already_lossy,
        exif_present=exif_present,
        icc_present=icc_present,
    )


def _norm(v: float, lo: float, hi: float) -> float:
    if hi <= lo:
        return 0.0
    return _clamp((v - lo) / (hi - lo))


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _mime_for(fmt: str) -> str:
    return {
        "JPEG": "image/jpeg", "JPG": "image/jpeg", "PNG": "image/png",
        "WEBP": "image/webp", "AVIF": "image/avif", "JXL": "image/jxl",
        "TIFF": "image/tiff", "BMP": "image/bmp", "GIF": "image/gif",
        "PPM": "image/x-portable-pixmap", "HEIC": "image/heic", "HEIF": "image/heif",
    }.get(fmt, "application/octet-stream")


def features_to_dict(f: ImageFeatures) -> dict:
    return asdict(f)
