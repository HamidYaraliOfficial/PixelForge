import os

import numpy as np
from PIL import Image

from pipeline.pipeline import process_single, PipelineOptions
from optimizer import Goal
from compression import AutoMode


def test_pipeline_end_to_end(tmp_path):
    arr = np.zeros((128, 128, 3), dtype=np.uint8)
    arr[:64, :64] = [10, 10, 10]
    arr[64:, 64:] = [240, 240, 240]
    path = str(tmp_path / "in.png")
    Image.fromarray(arr, "RGB").save(path)

    opt = PipelineOptions(goal=Goal.BALANCED, auto_mode=AutoMode.FAST, output_dir=str(tmp_path / "out"))
    report = process_single(path, opt)

    assert os.path.exists(report.output_path)
    assert report.original_size > 0
    assert report.final_size > 0
    assert 0.0 <= report.ssim <= 1.0
    assert isinstance(report.reasons, list) and len(report.reasons) > 0
