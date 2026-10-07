"""
PixelForge - Resize Engine
============================

Real resizing via Pillow's resampling filters, with support for exact target
dimensions, max width/height, and max megapixel caps (aspect ratio always
preserved unless both width AND height are given explicitly).
"""

from __future__ import annotations

from typing import Optional

from PIL import Image

_FILTERS = {
    "nearest": Image.NEAREST,
    "bilinear": Image.BILINEAR,
    "bicubic": Image.BICUBIC,
    "lanczos": Image.LANCZOS,
    "box": Image.BOX,
    "hamming": Image.HAMMING,
}


def suggest_filter(features) -> str:
    """Content-aware pick: sharp UI/line-art benefits from Lanczos or bicubic;
    photographic downscales look great with Lanczos too; heavy upscales of
    flat art can use bicubic to avoid ringing."""
    if features.line_art_score > 0.5 or features.screenshot_score > 0.5:
        return "bicubic"
    return "lanczos"


def resize_image(img: Image.Image, *, target_width: Optional[int] = None,
                  target_height: Optional[int] = None, max_width: Optional[int] = None,
                  max_height: Optional[int] = None, max_megapixels: Optional[float] = None,
                  filter_name: str = "lanczos") -> Image.Image:
    resample = _FILTERS.get(filter_name.lower(), Image.LANCZOS)
    w, h = img.size

    if target_width and target_height:
        return img.resize((int(target_width), int(target_height)), resample)

    if target_width:
        ratio = target_width / w
        return img.resize((int(target_width), max(1, round(h * ratio))), resample)

    if target_height:
        ratio = target_height / h
        return img.resize((max(1, round(w * ratio)), int(target_height)), resample)

    new_w, new_h = w, h

    if max_width and new_w > max_width:
        ratio = max_width / new_w
        new_w, new_h = max_width, max(1, round(new_h * ratio))

    if max_height and new_h > max_height:
        ratio = max_height / new_h
        new_w, new_h = max(1, round(new_w * ratio)), max_height

    if max_megapixels:
        cur_mp = (new_w * new_h) / 1_000_000
        if cur_mp > max_megapixels:
            ratio = (max_megapixels / cur_mp) ** 0.5
            new_w, new_h = max(1, round(new_w * ratio)), max(1, round(new_h * ratio))

    if (new_w, new_h) == (w, h):
        return img
    return img.resize((new_w, new_h), resample)
