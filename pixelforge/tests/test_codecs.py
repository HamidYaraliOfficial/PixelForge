import os

import numpy as np
import pytest
from PIL import Image

from imgcodecs import ENCODERS, available_codecs, safe_open, CorruptImageError

AVAILABLE = available_codecs()


def _sample_image(alpha=False):
    channels = 4 if alpha else 3
    arr = (np.random.rand(64, 64, channels) * 255).astype(np.uint8)
    return Image.fromarray(arr, "RGBA" if alpha else "RGB")


@pytest.mark.parametrize("fmt,kwargs", [
    ("JPEG", dict(quality=80)),
    ("PNG", dict(compress_level=6)),
    ("WEBP", dict(quality=80)),
    ("TIFF", dict(compression="tiff_lzw")),
    ("BMP", {}),
    ("GIF", {}),
    ("PPM", {}),
])
def test_roundtrip_always_available(tmp_path, fmt, kwargs):
    img = _sample_image()
    out = str(tmp_path / f"out.{fmt.lower()}")
    result = ENCODERS[fmt](img, out, **kwargs)
    assert os.path.exists(out)
    assert result.size_bytes > 0
    reopened = Image.open(out)
    reopened.load()
    assert reopened.size == img.size


@pytest.mark.skipif(not AVAILABLE["AVIF"], reason="AVIF plugin not installed")
def test_avif_roundtrip(tmp_path):
    img = _sample_image()
    out = str(tmp_path / "out.avif")
    result = ENCODERS["AVIF"](img, out, quality=50)
    assert os.path.exists(out) and result.size_bytes > 0


@pytest.mark.skipif(not AVAILABLE["JXL"], reason="JPEG XL plugin not installed")
def test_jxl_roundtrip(tmp_path):
    img = _sample_image()
    out = str(tmp_path / "out.jxl")
    result = ENCODERS["JXL"](img, out, distance=1.0)
    assert os.path.exists(out) and result.size_bytes > 0


@pytest.mark.skipif(not AVAILABLE["HEIF"], reason="HEIF plugin not installed")
def test_heif_roundtrip(tmp_path):
    img = _sample_image()
    out = str(tmp_path / "out.heif")
    result = ENCODERS["HEIF"](img, out, quality=80)
    assert os.path.exists(out) and result.size_bytes > 0


def test_corrupt_file_rejected(tmp_path):
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not an image")
    with pytest.raises(CorruptImageError):
        safe_open(str(bad))


def test_alpha_preserved_in_webp(tmp_path):
    img = _sample_image(alpha=True)
    out = str(tmp_path / "out.webp")
    ENCODERS["WEBP"](img, out, quality=80)
    reopened = Image.open(out)
    assert reopened.mode in ("RGBA", "P")
