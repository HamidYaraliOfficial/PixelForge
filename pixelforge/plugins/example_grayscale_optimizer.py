"""
Example PixelForge plugin: a "grayscale-optimized PNG" encoder.

Demonstrates the full plugin contract: a class implementing `encode`, plus a
module-level `register(registry)` function that PixelForge's plugin loader
calls automatically at startup (see plugins/base.py).

This is a real, working plugin - not a stub: it actually converts the image
to grayscale before PNG-encoding it, which is a genuinely useful one-click
option for documents/scans that don't need colour.
"""

from __future__ import annotations

import time

from plugins.base import PixelForgePlugin, PluginRegistry


class GrayscaleOptimizerPlugin(PixelForgePlugin):
    name = "grayscale-png-optimizer"
    version = "1.0.0"
    supported_formats = ["PNG_GRAY"]

    def encode(self, image, out_path: str, **params):
        from imgcodecs.registry import _result  # reuse the standard EncodeResult builder
        t0 = time.time()
        gray = image.convert("L")
        gray.save(out_path, format="PNG", optimize=True, compress_level=params.get("compress_level", 9))
        return _result(out_path, t0, "PNG_GRAY", params)


def register(registry: PluginRegistry) -> None:
    plugin = GrayscaleOptimizerPlugin()
    registry.register_encoder("PNG_GRAY", plugin.encode)
