import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


@dataclass
class HorizontalRun:
    x1: int
    x2: int
    y: int
    thickness: int

    @property
    def length(self) -> int:
        return self.x2 - self.x1 + 1


def parse_scale_distance_meters(scale: dict[str, Any]) -> float | None:
    candidates: list[float] = []
    for key in ("scale_text", "text", "label", "raw"):
        value = scale.get(key)
        if not value:
            continue
        text = str(value).replace("Ｍ", "M").replace("ｍ", "m")
        for number, unit in re.findall(r"(\d+(?:\.\d+)?)\s*(km|KM|Km|m|M|米|公里)?", text):
            amount = float(number)
            if amount <= 0:
                continue
            unit_text = unit or "m"
            if unit_text.lower() == "km" or unit_text == "公里":
                amount *= 1000
            candidates.append(amount)
    if not candidates:
        return None
    return max(candidates)


def _find_horizontal_runs(mask: np.ndarray, y_start: int, y_end: int) -> list[HorizontalRun]:
    height, width = mask.shape
    runs: list[HorizontalRun] = []
    for y in range(max(0, y_start), min(height, y_end)):
        xs = np.where(mask[y])[0]
        if xs.size == 0:
            continue
        start = int(xs[0])
        previous = int(xs[0])
        for raw_x in xs[1:]:
            x = int(raw_x)
            if x == previous + 1:
                previous = x
                continue
            _append_run(mask, runs, y, start, previous)
            start = previous = x
        _append_run(mask, runs, y, start, previous)
    return runs


def _append_run(mask: np.ndarray, runs: list[HorizontalRun], y: int, x1: int, x2: int) -> None:
    length = x2 - x1 + 1
    if length < 40 or length > mask.shape[1] * 0.35:
        return
    midpoint = (x1 + x2) // 2
    top = y
    bottom = y
    while top > 0 and mask[top - 1, midpoint]:
        top -= 1
    while bottom < mask.shape[0] - 1 and mask[bottom + 1, midpoint]:
        bottom += 1
    thickness = bottom - top + 1
    if 1 <= thickness <= 60:
        runs.append(HorizontalRun(x1=x1, x2=x2, y=y, thickness=thickness))


def _merge_runs(runs: list[HorizontalRun]) -> list[HorizontalRun]:
    merged: list[HorizontalRun] = []
    for run in sorted(runs, key=lambda item: (-item.length, item.y, item.x1)):
        is_duplicate = any(
            abs(run.y - item.y) <= 8 and abs(run.x1 - item.x1) <= 12 and abs(run.x2 - item.x2) <= 12
            for item in merged
        )
        if not is_duplicate:
            merged.append(run)
    return merged


def _score_scale_run(mask: np.ndarray, run: HorizontalRun, pixels: np.ndarray) -> float:
    height, width = mask.shape
    search_top = max(0, run.y - 55)
    search_bottom = min(height, run.y + 55)
    segment_width = max(2, min(12, run.length // 40))
    tick_score = 0
    tick_extents: list[int] = []
    for x in (run.x1, (run.x1 + run.x2) // 2, run.x2):
        left = max(0, x - segment_width)
        right = min(width, x + segment_width + 1)
        column_hits = mask[search_top:search_bottom, left:right].sum(axis=1)
        vertical_extent_rows = np.where(column_hits > 0)[0]
        extent = int(vertical_extent_rows[-1] - vertical_extent_rows[0] + 1) if vertical_extent_rows.size else 0
        tick_extents.append(extent)
        if 18 <= extent <= 90:
            tick_score += 1

    line_band_top = max(0, run.y - 4)
    line_band_bottom = min(height, run.y + 5)
    long_line_rows = mask[line_band_top:line_band_bottom, :].sum(axis=1)
    row_dark_width = int(long_line_rows.max()) if long_line_rows.size else 0
    border_penalty = 5 if row_dark_width > run.length * 1.6 else 0

    empty_above = 0
    above_top = max(0, run.y - 220)
    above_bottom = max(0, run.y - 90)
    if above_bottom > above_top:
        above = mask[above_top:above_bottom, max(0, run.x1 - 60) : min(width, run.x2 + 60)]
        if float(above.mean()) < 0.03:
            empty_above = 1

    white_margin = 0
    margin = 35
    left = max(0, run.x1 - margin)
    right = min(width, run.x2 + margin)
    top = max(0, run.y - margin)
    bottom = min(height, run.y + margin)
    local_dark_ratio = float(mask[top:bottom, left:right].mean()) if bottom > top and right > left else 1.0
    if local_dark_ratio < 0.08:
        white_margin = 1
    color_region = pixels[top:bottom, left:right]
    if color_region.size:
        is_white = (color_region[:, :, 0] > 235) & (color_region[:, :, 1] > 235) & (color_region[:, :, 2] > 235)
        is_dark = (color_region[:, :, 0] < 100) & (color_region[:, :, 1] < 100) & (color_region[:, :, 2] < 100)
        colored_ratio = float((~is_white & ~is_dark).mean())
    else:
        colored_ratio = 1.0
    colored_penalty = 6 if colored_ratio > 0.12 else 0
    preferred_length = 1.0 if width * 0.04 <= run.length <= width * 0.18 else 0.0
    length_score = min(run.length / 600, 1.0)
    return tick_score * 4 + white_margin + empty_above + preferred_length + length_score - border_penalty - colored_penalty


def estimate_scale_from_image(image_path: str | Path, scale: dict[str, Any]) -> dict[str, Any]:
    scale = dict(scale)
    if scale.get("note") == "LLM未能确定比例尺，已使用默认值，可在数据库中修正":
        scale.pop("note", None)
    distance_meters = parse_scale_distance_meters(scale)
    if distance_meters is None:
        return {**scale, "scale_detection": {"status": "no_scale_distance_text"}}

    image = Image.open(image_path).convert("RGB")
    pixels = np.asarray(image)
    height, width = pixels.shape[:2]
    dark_mask = (pixels[:, :, 0] < 85) & (pixels[:, :, 1] < 85) & (pixels[:, :, 2] < 85)
    runs = _merge_runs(_find_horizontal_runs(dark_mask, int(height * 0.05), int(height * 0.9)))
    if not runs:
        return {**scale, "scale_detection": {"status": "no_horizontal_scale_candidate", "distance_meters": distance_meters}}

    candidates = sorted(
        (
            {
                "x1": run.x1,
                "x2": run.x2,
                "y": run.y,
                "pixel_length": run.length,
                "score": round(_score_scale_run(dark_mask, run, pixels), 3),
            }
            for run in runs
            if run.length >= 80
        ),
        key=lambda item: (item["score"], item["pixel_length"]),
        reverse=True,
    )
    if not candidates or candidates[0]["score"] < 3:
        return {
            **scale,
            "scale_detection": {
                "status": "low_confidence",
                "distance_meters": distance_meters,
                "candidates": candidates[:5],
            },
        }

    best = candidates[0]
    meters_per_pixel = distance_meters / float(best["pixel_length"])
    return {
        **scale,
        "meters_per_pixel": meters_per_pixel,
        "scale_detection": {
            "status": "estimated_from_scale_bar",
            "distance_meters": distance_meters,
            "pixel_length": best["pixel_length"],
            "bbox": {"x1": best["x1"], "y": best["y"], "x2": best["x2"]},
            "score": best["score"],
            "candidates": candidates[:5],
        },
    }
