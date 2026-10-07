"""
PixelForge - Plugin SDK
==========================

A minimal, real plugin architecture: drop a .py file implementing
``PixelForgePlugin`` into the plugins directory and expose a module-level
``register(registry)`` function. PixelForge discovers and loads it at
startup, registering any additional codecs it provides into
``imgcodecs.ENCODERS`` (or additional analysis hooks in the future).

See ``plugins/example_grayscale_optimizer.py`` for a complete, working
example plugin.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass

logger = logging.getLogger("pixelforge.plugins")


class PixelForgePlugin(ABC):
    name: str = "unnamed-plugin"
    version: str = "0.1.0"
    supported_formats: list[str] = []

    @abstractmethod
    def encode(self, image, out_path: str, **params):
        ...

    def describe(self) -> dict:
        return {"name": self.name, "version": self.version, "supported_formats": self.supported_formats}


@dataclass
class PluginRegistry:
    encoders: dict

    def register_encoder(self, format_name: str, encode_fn) -> None:
        self.encoders[format_name] = encode_fn
        logger.info("Plugin registered encoder for format: %s", format_name)


def load_plugins(plugins_dir: str, registry: PluginRegistry) -> list[str]:
    """Scans `plugins_dir` for *.py files (except this one) and calls their
    module-level `register(registry)` function, if present. Returns the list
    of successfully loaded plugin module names."""
    loaded = []
    if not os.path.isdir(plugins_dir):
        return loaded
    for fname in os.listdir(plugins_dir):
        if not fname.endswith(".py") or fname in ("base.py", "__init__.py"):
            continue
        path = os.path.join(plugins_dir, fname)
        mod_name = f"pixelforge_plugin_{os.path.splitext(fname)[0]}"
        try:
            spec = importlib.util.spec_from_file_location(mod_name, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = module
            spec.loader.exec_module(module)  # type: ignore[union-attr]
            if hasattr(module, "register"):
                module.register(registry)
                loaded.append(mod_name)
        except Exception:
            logger.exception("Failed to load plugin %s", fname)
    return loaded
