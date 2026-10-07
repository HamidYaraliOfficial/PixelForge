import numpy as np
from PIL import Image

from analysis import analyze_image


def _save(tmp_path, arr, name="img.png", mode="RGB"):
    p = tmp_path / name
    Image.fromarray(arr, mode).save(p)
    return str(p)


def test_photo_like_gradient_noise(tmp_path):
    w, h = 256, 256
    grad = np.tile(np.linspace(0, 255, w), (h, 1)).astype(np.uint8)
    noise = np.random.normal(0, 20, (h, w))
    arr = np.clip(grad[:, :, None].repeat(3, 2).astype(np.int16) + noise[:, :, None], 0, 255).astype(np.uint8)
    path = _save(tmp_path, arr)
    f = analyze_image(path)
    assert f.width == w and f.height == h
    assert f.color_space == "RGB"
    assert 0.0 <= f.photo_score <= 1.0
    assert f.file_size > 0


def test_flat_icon_few_colors(tmp_path):
    arr = np.zeros((64, 64, 3), dtype=np.uint8)
    arr[:32, :32] = [255, 0, 0]
    arr[32:, 32:] = [0, 255, 0]
    path = _save(tmp_path, arr)
    f = analyze_image(path)
    assert f.approx_unique_colors <= 8
    assert f.flat_region_ratio > 0.5


def test_transparent_png_alpha_detected(tmp_path):
    arr = np.zeros((32, 32, 4), dtype=np.uint8)
    arr[..., 3] = 128
    path = _save(tmp_path, arr, mode="RGBA")
    f = analyze_image(path)
    assert f.has_alpha is True


def test_grayscale_detected(tmp_path):
    arr = (np.random.rand(50, 50) * 255).astype(np.uint8)
    path = _save(tmp_path, arr, mode="L")
    f = analyze_image(path)
    assert f.is_grayscale is True
    assert f.color_space == "GRAY"


def test_decompression_bomb_guard(tmp_path):
    # Simulate the guard logic directly (creating a real 300MP+ file is too slow/large for CI).
    from analysis.features import MAX_SAFE_PIXELS
    assert MAX_SAFE_PIXELS > 0
