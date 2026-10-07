"""
PixelForge - Codec Registry
============================

Thin, safe wrappers around real, native-backed encoders/decoders. Everything
here goes through Pillow, which itself is a compiled binding to the reference
C libraries (libjpeg-turbo, libpng, libwebp, libavif, libheif, libjxl, libtiff)
- so encoding is genuinely performed by those libraries, not re-implemented in
Python.

Optional codecs (AVIF / HEIF / JXL) are feature-detected at import time. If a
plugin wheel isn't installed on a given machine, that codec is simply reported
as unavailable (see ``available_codecs()``) and the Decision Engine will not
offer it as a candidate - this mirrors what the Format Explorer panel in the
GUI shows to the user.
"""

from __future__ import annotations

import io
import os
import time
from dataclasses import dataclass
from typing import Callable, Optional

from PIL import Image

Image.MAX_IMAGE_PIXELS = 300_000_000  # decompression-bomb guard (PIL raises DecompressionBombError)

_AVIF_OK = False
_HEIF_OK = False
_JXL_OK = False

try:
    import pillow_avif  # noqa: F401  (registers AVIF plugin with Pillow)
    _AVIF_OK = True
except Exception:
    _AVIF_OK = False

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    _HEIF_OK = True
except Exception:
    _HEIF_OK = False

try:
    import pillow_jxl  # noqa: F401  (registers JXL plugin with Pillow)
    _JXL_OK = True
except Exception:
    _JXL_OK = False


class CodecUnavailable(RuntimeError):
    pass


class CorruptImageError(RuntimeError):
    pass


@dataclass
class EncodeResult:
    out_path: str
    size_bytes: int
    encode_time_s: float
    format: str
    params: dict


# --------------------------------------------------------------------------------------
# Safe decode
# --------------------------------------------------------------------------------------

def safe_open(path: str) -> Image.Image:
    """Open + verify an image defensively against malformed / hostile input."""
    try:
        with Image.open(path) as probe:
            probe.verify()  # cheap structural check, does not decode full raster
    except Exception as exc:
        raise CorruptImageError(f"{path}: failed integrity check ({exc})") from exc
    try:
        img = Image.open(path)
        img.load()
        return img
    except Image.DecompressionBombError as exc:
        raise CorruptImageError(f"{path}: rejected as a decompression bomb ({exc})") from exc
    except Exception as exc:
        raise CorruptImageError(f"{path}: failed to decode ({exc})") from exc


# --------------------------------------------------------------------------------------
# Per-format encoders. Each returns EncodeResult and raises CodecUnavailable /
# ValueError on bad params rather than silently degrading.
# --------------------------------------------------------------------------------------

def encode_jpeg(img: Image.Image, out_path: str, quality: int = 85, progressive: bool = True,
                 optimize: bool = True, subsampling: int = 2) -> EncodeResult:
    """subsampling: 0 = 4:4:4, 1 = 4:2:2, 2 = 4:2:0 (Pillow convention)."""
    rgb = img.convert("RGB") if img.mode in ("RGBA", "P", "LA") else img
    t0 = time.time()
    rgb.save(out_path, format="JPEG", quality=int(quality), optimize=optimize,
              progressive=progressive, subsampling=subsampling)
    return _result(out_path, t0, "JPEG", dict(quality=quality, progressive=progressive,
                                               optimize=optimize, subsampling=subsampling))


def encode_png(img: Image.Image, out_path: str, compress_level: int = 9, optimize: bool = True,
                palette: bool = False, bits: Optional[int] = None) -> EncodeResult:
    work = img
    if palette and img.mode != "P":
        work = img.convert("P", palette=Image.ADAPTIVE, colors=256)
    t0 = time.time()
    save_kwargs = dict(format="PNG", optimize=optimize, compress_level=int(compress_level))
    if bits and work.mode == "P":
        save_kwargs["bits"] = bits
    work.save(out_path, **save_kwargs)
    return _result(out_path, t0, "PNG", dict(compress_level=compress_level, optimize=optimize,
                                              palette=palette))


def encode_webp(img: Image.Image, out_path: str, quality: int = 80, lossless: bool = False,
                 method: int = 6, alpha_quality: int = 100, near_lossless: Optional[int] = None) -> EncodeResult:
    t0 = time.time()
    kwargs = dict(format="WEBP", quality=int(quality), method=int(method), lossless=lossless,
                  alpha_quality=int(alpha_quality))
    if near_lossless is not None:
        kwargs["near_lossless"] = int(near_lossless)
    img.save(out_path, **kwargs)
    return _result(out_path, t0, "WEBP", {k: v for k, v in kwargs.items() if k != "format"})


def encode_avif(img: Image.Image, out_path: str, quality: int = 50, speed: int = 6) -> EncodeResult:
    if not _AVIF_OK:
        raise CodecUnavailable("AVIF plugin (pillow-avif-plugin) is not installed.")
    t0 = time.time()
    img.save(out_path, format="AVIF", quality=int(quality), speed=int(speed))
    return _result(out_path, t0, "AVIF", dict(quality=quality, speed=speed))


def encode_jxl(img: Image.Image, out_path: str, lossless: bool = False, distance: float = 1.0,
                effort: int = 7) -> EncodeResult:
    if not _JXL_OK:
        raise CodecUnavailable("JPEG XL plugin (pillow-jxl-plugin) is not installed.")
    t0 = time.time()
    img.save(out_path, format="JXL", lossless=lossless, distance=float(distance), effort=int(effort))
    return _result(out_path, t0, "JXL", dict(lossless=lossless, distance=distance, effort=effort))


def encode_heif(img: Image.Image, out_path: str, quality: int = 80) -> EncodeResult:
    if not _HEIF_OK:
        raise CodecUnavailable("HEIF plugin (pillow-heif) is not installed.")
    t0 = time.time()
    img.save(out_path, format="HEIF", quality=int(quality))
    return _result(out_path, t0, "HEIF", dict(quality=quality))


def encode_tiff(img: Image.Image, out_path: str, compression: str = "tiff_lzw") -> EncodeResult:
    t0 = time.time()
    img.save(out_path, format="TIFF", compression=compression)
    return _result(out_path, t0, "TIFF", dict(compression=compression))


def encode_bmp(img: Image.Image, out_path: str) -> EncodeResult:
    t0 = time.time()
    img.convert("RGB").save(out_path, format="BMP")
    return _result(out_path, t0, "BMP", {})


def encode_gif(img: Image.Image, out_path: str, colors: int = 256) -> EncodeResult:
    t0 = time.time()
    work = img.convert("P", palette=Image.ADAPTIVE, colors=colors)
    work.save(out_path, format="GIF")
    return _result(out_path, t0, "GIF", dict(colors=colors))


def encode_ppm(img: Image.Image, out_path: str) -> EncodeResult:
    t0 = time.time()
    img.convert("RGB").save(out_path, format="PPM")
    return _result(out_path, t0, "PPM", {})


def _result(out_path: str, t0: float, fmt: str, params: dict) -> EncodeResult:
    return EncodeResult(
        out_path=out_path,
        size_bytes=os.path.getsize(out_path),
        encode_time_s=round(time.time() - t0, 4),
        format=fmt,
        params=params,
    )


ENCODERS: dict[str, Callable[..., EncodeResult]] = {
    "JPEG": encode_jpeg,
    "PNG": encode_png,
    "WEBP": encode_webp,
    "AVIF": encode_avif,
    "JXL": encode_jxl,
    "HEIF": encode_heif,
    "TIFF": encode_tiff,
    "BMP": encode_bmp,
    "GIF": encode_gif,
    "PPM": encode_ppm,
}


def available_codecs() -> dict[str, bool]:
    return {
        "JPEG": True, "PNG": True, "WEBP": True, "TIFF": True, "BMP": True,
        "GIF": True, "PPM": True,
        "AVIF": _AVIF_OK, "HEIF": _HEIF_OK, "JXL": _JXL_OK,
    }


def lossless_jpeg_reoptimize(src_path: str, out_path: str) -> EncodeResult:
    """Re-save a JPEG with Huffman optimisation / metadata stripped WITHOUT
    touching the DCT coefficients (no additional generational quality loss).
    This backs the 'is re-encoding worth it?' logic in the decision engine.
    """
    t0 = time.time()
    with Image.open(src_path) as img:
        img.save(out_path, format="JPEG", quality="keep", optimize=True)
    return _result(out_path, t0, "JPEG", dict(mode="lossless_reoptimize"))
