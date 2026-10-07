"""
PixelForge - Duplicate Detection
===================================

Real perceptual hashing (phash / dhash / ahash via the `imagehash` library,
itself built on Pillow + NumPy) plus SHA-256 for exact-duplicate detection.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Optional

import imagehash
from PIL import Image


@dataclass
class HashInfo:
    path: str
    sha256: str
    phash: str
    dhash: str
    ahash: str


def compute_hashes(path: str) -> HashInfo:
    with Image.open(path) as img:
        rgb = img.convert("RGB")
        phash = str(imagehash.phash(rgb))
        dhash = str(imagehash.dhash(rgb))
        ahash = str(imagehash.average_hash(rgb))
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            sha.update(chunk)
    return HashInfo(path=path, sha256=sha.hexdigest(), phash=phash, dhash=dhash, ahash=ahash)


def hamming_distance(hex_a: str, hex_b: str) -> int:
    return imagehash.hex_to_hash(hex_a) - imagehash.hex_to_hash(hex_b)


def find_duplicates(paths: list[str], phash_threshold: int = 5) -> list[list[str]]:
    """Groups files that are byte-identical OR perceptually near-identical
    (Hamming distance <= phash_threshold)."""
    infos = [compute_hashes(p) for p in paths]

    groups: list[list[HashInfo]] = []
    used = set()
    for i, a in enumerate(infos):
        if i in used:
            continue
        group = [a]
        used.add(i)
        for j in range(i + 1, len(infos)):
            if j in used:
                continue
            b = infos[j]
            if a.sha256 == b.sha256 or hamming_distance(a.phash, b.phash) <= phash_threshold:
                group.append(b)
                used.add(j)
        if len(group) > 1:
            groups.append([g.path for g in group])
    return groups
