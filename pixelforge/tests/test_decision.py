import numpy as np
from PIL import Image

from analysis import analyze_image
from optimizer import decide, Goal


def _save(tmp_path, arr, name="img.png", mode="RGB"):
    p = tmp_path / name
    Image.fromarray(arr, mode).save(p)
    return str(p)


def test_determinism(tmp_path):
    arr = np.zeros((64, 64, 3), dtype=np.uint8)
    arr[:32, :32] = [200, 30, 30]
    path = _save(tmp_path, arr)
    f = analyze_image(path)
    r1 = decide(f, Goal.BALANCED)
    r2 = decide(f, Goal.BALANCED)
    assert [c.format for c in r1.candidates] == [c.format for c in r2.candidates]


def test_alpha_excludes_jpeg(tmp_path):
    arr = np.zeros((32, 32, 4), dtype=np.uint8)
    arr[..., 3] = 100
    path = _save(tmp_path, arr, mode="RGBA")
    f = analyze_image(path)
    d = decide(f, Goal.BALANCED)
    assert "JPEG" not in [c.format for c in d.candidates]


def test_already_jpeg_skips_reencode(tmp_path):
    arr = (np.random.rand(64, 64, 3) * 255).astype(np.uint8)
    path = str(tmp_path / "img.jpg")
    Image.fromarray(arr, "RGB").save(path, format="JPEG", quality=85)
    f = analyze_image(path)
    d = decide(f, Goal.BALANCED)
    assert d.skip_reencode is True


def test_max_quality_returns_candidates(tmp_path):
    arr = (np.random.rand(64, 64, 3) * 255).astype(np.uint8)
    path = _save(tmp_path, arr)
    f = analyze_image(path)
    d = decide(f, Goal.MAX_QUALITY)
    assert len(d.candidates) > 0
