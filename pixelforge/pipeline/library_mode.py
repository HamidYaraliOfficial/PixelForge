"""
PixelForge - Smart Library Mode
==================================

Scans a folder of images and, for each file, runs a FAST estimate: real
analysis + a cheap single-candidate encode (no full benchmark) to project the
likely savings and recommended format, without committing to overwrite
anything. Intended for "how much could I save if I ran Auto-Compress on this
whole library?" style questions.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, asdict

from analysis import analyze_image
from imgcodecs import safe_open, ENCODERS, CorruptImageError
from optimizer import decide, Goal
from quality.metrics import compute_metrics

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".avif", ".jxl", ".tif", ".tiff",
                    ".bmp", ".gif", ".ppm", ".pgm", ".pnm", ".heic", ".heif"}


@dataclass
class LibraryEntry:
    path: str
    current_size: int
    suggested_format: str
    estimated_new_size: int
    estimated_savings_percent: float
    worth_converting: bool
    reason: str


def scan_folder(root: str, recursive: bool = True, goal: Goal = Goal.BALANCED) -> list[LibraryEntry]:
    entries: list[LibraryEntry] = []
    walker = os.walk(root) if recursive else [(root, [], os.listdir(root))]
    for dirpath, _dirs, filenames in walker:
        for name in filenames:
            ext = os.path.splitext(name)[1].lower()
            if ext not in IMAGE_EXTENSIONS:
                continue
            full = os.path.join(dirpath, name)
            try:
                entries.append(_estimate_one(full, goal))
            except (CorruptImageError, Exception) as exc:  # noqa: BLE001 - library scan must not crash
                entries.append(LibraryEntry(full, os.path.getsize(full) if os.path.exists(full) else 0,
                                             "N/A", 0, 0.0, False, f"Skipped: {exc}"))
    return entries


def _estimate_one(path: str, goal: Goal) -> LibraryEntry:
    img = safe_open(path)
    features = analyze_image(path, img)
    decision = decide(features, goal)
    if not decision.candidates:
        return LibraryEntry(path, features.file_size, features.format, features.file_size, 0.0, False,
                             "No better candidate found.")

    top = decision.candidates[0]
    encoder = ENCODERS.get(top.format)
    if encoder is None:
        return LibraryEntry(path, features.file_size, features.format, features.file_size, 0.0, False,
                             "Preferred codec unavailable on this system.")

    tmp = tempfile.mktemp(suffix=f".{top.format.lower()}")
    try:
        result = encoder(img, tmp, **top.params)
        new_size = result.size_bytes
        savings = round(100.0 * (features.file_size - new_size) / max(1, features.file_size), 2)
        m = compute_metrics(path, tmp)
        worth_it = savings > 5 and m.ssim > 0.85
        reason = (decision.reasons[0] if decision.reasons else "") + \
                 (f" Estimated SSIM {m.ssim:.3f}." if worth_it else f" Low projected benefit (SSIM {m.ssim:.3f}).")
        return LibraryEntry(path, features.file_size, top.format, new_size, savings, worth_it, reason)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def summarize(entries: list[LibraryEntry]) -> dict:
    total_current = sum(e.current_size for e in entries)
    total_new = sum(e.estimated_new_size for e in entries if e.worth_converting) + \
        sum(e.current_size for e in entries if not e.worth_converting)
    return {
        "files_scanned": len(entries),
        "current_total_bytes": total_current,
        "projected_total_bytes": total_new,
        "projected_savings_bytes": total_current - total_new,
        "projected_savings_percent": round(100.0 * (total_current - total_new) / max(1, total_current), 2),
        "files_worth_converting": sum(1 for e in entries if e.worth_converting),
    }
