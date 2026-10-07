"""
PixelForge - Custom Rule Engine
=================================

Lets power users define simple condition -> action rules evaluated per file
during batch processing, e.g.:

    Rule(
        name="skip PNG without alpha",
        condition={"format": "PNG", "has_alpha": False},
        action={"try_formats": ["AVIF", "WEBP", "JPEG"]},
    )
    Rule(
        name="keep original if barely smaller",
        condition={"always": True},
        action={"min_reduction_percent": 5, "on_fail": "keep_original"},
    )
    Rule(
        name="quality floor",
        condition={"always": True},
        action={"min_ssim": 0.9, "on_fail": "keep_original"},
    )

Conditions are a small, safe dict-based DSL (no eval()) matched against the
image's ``ImageFeatures``. Actions are interpreted by the pipeline after the
compression run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from analysis.features import ImageFeatures


@dataclass
class Rule:
    name: str
    condition: dict[str, Any]
    action: dict[str, Any]
    enabled: bool = True


_COMPARATORS = {
    "gt": lambda a, b: a > b,
    "gte": lambda a, b: a >= b,
    "lt": lambda a, b: a < b,
    "lte": lambda a, b: a <= b,
    "eq": lambda a, b: a == b,
    "neq": lambda a, b: a != b,
}


def matches(features: ImageFeatures, condition: dict[str, Any]) -> bool:
    if condition.get("always"):
        return True
    fdict = features.__dict__
    for key, expected in condition.items():
        if key == "always":
            continue
        if isinstance(expected, dict) and set(expected.keys()) & set(_COMPARATORS.keys()):
            actual = fdict.get(key)
            for op, val in expected.items():
                cmp = _COMPARATORS.get(op)
                if cmp is None or actual is None or not cmp(actual, val):
                    return False
        else:
            if fdict.get(key) != expected:
                return False
    return True


def applicable_rules(features: ImageFeatures, rules: list[Rule]) -> list[Rule]:
    return [r for r in rules if r.enabled and matches(features, r.condition)]


def try_formats_override(rules: list[Rule], features: ImageFeatures) -> list[str] | None:
    for r in applicable_rules(features, rules):
        if "try_formats" in r.action:
            return list(r.action["try_formats"])
    return None


def post_process_gates(rules: list[Rule], features: ImageFeatures,
                        reduction_percent: float, ssim: float) -> tuple[bool, list[str]]:
    """Returns (keep_new_output, messages). If any active gate fails, the batch
    processor should keep the ORIGINAL file instead of the compressed output."""
    keep_new = True
    messages: list[str] = []
    for r in applicable_rules(features, rules):
        if "min_reduction_percent" in r.action and reduction_percent < r.action["min_reduction_percent"]:
            keep_new = False
            messages.append(f"Rule '{r.name}': reduction {reduction_percent:.1f}% below required "
                             f"{r.action['min_reduction_percent']}% -> keeping original.")
        if "min_ssim" in r.action and ssim < r.action["min_ssim"]:
            keep_new = False
            messages.append(f"Rule '{r.name}': SSIM {ssim:.3f} below required "
                             f"{r.action['min_ssim']} -> keeping original.")
        if "max_size_mb_trigger" in r.action:
            pass  # evaluated earlier, at file-selection time, by the batch queue
    return keep_new, messages
