"""
PixelForge - Metadata Manager
================================

Reads and controls EXIF / ICC-profile metadata on the way out. Supports three
policies (keep_all / keep_selected / remove_all) and an independent
Privacy Mode switch that always strips GPS + other sensitive EXIF tags
regardless of the chosen policy.
"""

from __future__ import annotations

from typing import Optional

from PIL import Image, ExifTags

# EXIF GPS IFD tag id
_GPS_TAG_ID = next((k for k, v in ExifTags.TAGS.items() if v == "GPSInfo"), 34853)

_SENSITIVE_TAG_NAMES = {"GPSInfo", "SerialNumber", "BodySerialNumber", "LensSerialNumber", "OwnerName", "CameraOwnerName"}


def read_metadata(path: str) -> dict:
    info = {}
    with Image.open(path) as img:
        exif = img.getexif()
        if exif:
            info["exif"] = {ExifTags.TAGS.get(k, str(k)): v for k, v in exif.items()}
        info["icc_profile_present"] = "icc_profile" in img.info
        info["dpi"] = img.info.get("dpi")
        info["has_gps"] = bool(exif and _GPS_TAG_ID in exif)
    return info


def apply_metadata_policy(img: Image.Image, policy: str = "keep_selected",
                           keep_keys: Optional[list[str]] = None,
                           privacy_mode: bool = False) -> dict:
    """Returns a dict of save-kwargs (e.g. {'exif': b'...', 'icc_profile': b'...'})
    to merge into an encoder call, according to the requested policy."""
    save_kwargs: dict = {}

    if policy == "remove_all":
        return save_kwargs  # nothing carried over

    exif = img.getexif()
    if not exif:
        return save_kwargs

    if policy == "keep_all" and not privacy_mode:
        save_kwargs["exif"] = exif.tobytes()
    else:
        keep_keys = keep_keys or []
        filtered = Image.Exif()
        for tag_id, value in exif.items():
            name = ExifTags.TAGS.get(tag_id, str(tag_id))
            if privacy_mode and name in _SENSITIVE_TAG_NAMES:
                continue
            if policy == "keep_selected" and keep_keys and name not in keep_keys:
                continue
            filtered[tag_id] = value
        if len(filtered):
            save_kwargs["exif"] = filtered.tobytes()

    if "icc_profile" in img.info:
        save_kwargs["icc_profile"] = img.info["icc_profile"]

    return save_kwargs
