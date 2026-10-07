"""
PixelForge - Intelligent Preset Engine
========================================

Presets are convenient *starting points*: a goal plus optional dimension /
metadata constraints for a common use case. The Decision Engine still runs on
top of them and can override format choice based on the actual image content -
e.g. picking the "Transparent Image" preset on a JPEG (which cannot have
alpha) will simply fall back to the engine's normal photographic path.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional

from optimizer.decision import Goal


@dataclass
class Preset:
    name: str
    goal: Goal
    max_width: Optional[int] = None
    max_height: Optional[int] = None
    max_megapixels: Optional[float] = None
    metadata_policy: str = "keep_selected"   # keep_all | keep_selected | remove_all
    privacy_mode: bool = False
    description: str = ""


BUILTIN_PRESETS: dict[str, Preset] = {
    "web_photo": Preset("web_photo", Goal.WEB_OPTIMIZED, max_width=2048, metadata_policy="remove_all",
                         description="General photos for websites/blogs."),
    "ecommerce": Preset("ecommerce", Goal.BALANCED, max_width=2000, max_height=2000,
                         metadata_policy="remove_all", privacy_mode=True,
                         description="Product photography - consistent square-ish sizing, clean metadata."),
    "social_media": Preset("social_media", Goal.WEB_OPTIMIZED, max_width=1600, metadata_policy="remove_all",
                            privacy_mode=True, description="Optimised for social platforms; strips GPS/EXIF."),
    "website_hero": Preset("website_hero", Goal.BALANCED, max_width=2560, metadata_policy="remove_all",
                            description="Large hero/banner images."),
    "thumbnail": Preset("thumbnail", Goal.MAX_COMPRESSION, max_width=400, max_height=400,
                         metadata_policy="remove_all", description="Small preview thumbnails."),
    "screenshot": Preset("screenshot", Goal.BALANCED, metadata_policy="remove_all",
                          description="UI screenshots - biased toward lossless/near-lossless."),
    "document_scan": Preset("document_scan", Goal.MAX_QUALITY, metadata_policy="keep_all",
                             description="Scanned documents - prioritises text legibility."),
    "transparent_image": Preset("transparent_image", Goal.BALANCED, metadata_policy="remove_all",
                                 description="Logos/graphics that require alpha transparency."),
    "archive_lossless": Preset("archive_lossless", Goal.MAX_QUALITY, metadata_policy="keep_all",
                                description="Long-term archival - lossless only, all metadata kept."),
    "mobile": Preset("mobile", Goal.WEB_OPTIMIZED, max_width=1280, metadata_policy="remove_all",
                      privacy_mode=True, description="Optimised for mobile bandwidth/screens."),
    "email_attachment": Preset("email_attachment", Goal.MAX_COMPRESSION, max_width=1600,
                                metadata_policy="remove_all",
                                description="Small enough to attach to email comfortably."),
    "maximum_compression": Preset("maximum_compression", Goal.MAX_COMPRESSION, metadata_policy="remove_all",
                                   description="Smallest possible file, quality is secondary."),
}


def get_preset(name: str) -> Optional[Preset]:
    return BUILTIN_PRESETS.get(name)


def list_presets() -> list[dict]:
    return [asdict(p) for p in BUILTIN_PRESETS.values()]
