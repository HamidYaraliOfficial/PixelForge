import numpy as np
from PIL import Image

from compression.target_size import compress_to_target_size


def test_target_size_converges(tmp_path):
    arr = (np.random.rand(200, 200, 3) * 255).astype(np.uint8)
    img = Image.fromarray(arr, "RGB")
    target = 8000
    out = str(tmp_path / "out.jpg")
    result = compress_to_target_size(img, "JPEG", target, out_path=out, tolerance=0.15)
    assert result.size_bytes > 0
    assert abs(result.size_bytes - target) <= target * 0.5  # sanity bound, not exact
    assert result.iterations > 0
