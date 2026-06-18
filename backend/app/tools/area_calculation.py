from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
import json
from math import floor, sqrt
from pathlib import Path
from typing import Any, Iterable, Literal

import numpy as np
from PIL import Image, ImageColor, ImageDraw

ShapeType = Literal["polygon", "circle"]
MIN_VISIBLE_MATCH_RATIO = 0.005
MAX_NOISE_PIXELS = 50
FALLBACK_MATCH_TOLERANCE = 26.0
FALLBACK_MATCH_MIN_MARGIN = 4.0
FALLBACK_MATCH_MAX_RATIO = 0.88
FALLBACK_MATCH_MIN_PIXELS = 24
COMPONENT_GROW_DELTA_E = 10.5
COMPONENT_SEED_DELTA_E = 16.0
COMPONENT_MIN_PIXELS = 20
FILL_MIN_CHROMA = 18
AREA_DEBUG_DIR = Path(__file__).resolve().parents[2] / "data" / "area_debug"


@dataclass
class Shape:
    type: ShapeType
    points: list[dict[str, float]] | None = None
    center: dict[str, float] | None = None
    radius: float | None = None


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    return ImageColor.getrgb(hex_color.strip())[:3]


def point_in_polygon(x: float, y: float, points: list[dict[str, float]]) -> bool:
    inside = False
    previous = points[-1]
    for current in points:
        xi, yi = current["x"], current["y"]
        xj, yj = previous["x"], previous["y"]
        intersects = (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi
        if intersects:
            inside = not inside
        previous = current
    return inside


def normalize_shape_payload(payload: dict[str, Any]) -> dict[str, Any]:
    shape_type = payload.get("type")
    if shape_type == "polygon":
        return {"type": "polygon", "points": payload.get("points", [])}
    if shape_type == "circle":
        return {
            "type": "circle",
            "center": payload.get("center", {"x": 0.0, "y": 0.0}),
            "radius": float(payload.get("radius", 0.0) or 0.0),
        }
    raise ValueError("Unsupported shape type")


def iter_shape_pixels(shape: Shape, width: int, height: int) -> Iterable[tuple[int, int]]:
    if shape.type == "polygon":
        if not shape.points or len(shape.points) < 3:
            return
        min_x = max(0, floor(min(p["x"] for p in shape.points)))
        max_x = min(width - 1, floor(max(p["x"] for p in shape.points)))
        min_y = max(0, floor(min(p["y"] for p in shape.points)))
        max_y = min(height - 1, floor(max(p["y"] for p in shape.points)))
        for y in range(min_y, max_y + 1):
            for x in range(min_x, max_x + 1):
                if point_in_polygon(x + 0.5, y + 0.5, shape.points):
                    yield x, y
    elif shape.type == "circle":
        if not shape.center or not shape.radius:
            return
        cx, cy, radius = shape.center["x"], shape.center["y"], shape.radius
        min_x = max(0, floor(cx - radius))
        max_x = min(width - 1, floor(cx + radius))
        min_y = max(0, floor(cy - radius))
        max_y = min(height - 1, floor(cy + radius))
        radius_sq = radius * radius
        for y in range(min_y, max_y + 1):
            for x in range(min_x, max_x + 1):
                if (x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2 <= radius_sq:
                    yield x, y


def create_shape_mask(shape: Shape, width: int, height: int) -> np.ndarray:
    mask_image = Image.new("1", (width, height), 0)
    draw = ImageDraw.Draw(mask_image)
    if shape.type == "polygon":
        if not shape.points or len(shape.points) < 3:
            return np.zeros((height, width), dtype=bool)
        polygon = [(float(point["x"]), float(point["y"])) for point in shape.points]
        draw.polygon(polygon, fill=1)
    elif shape.type == "circle":
        if not shape.center or not shape.radius:
            return np.zeros((height, width), dtype=bool)
        cx, cy, radius = float(shape.center["x"]), float(shape.center["y"]), float(shape.radius)
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=1)
    return np.asarray(mask_image, dtype=bool)


def rgb_to_hex(rgb: np.ndarray | tuple[int, int, int]) -> str:
    red, green, blue = [int(value) for value in rgb]
    return f"#{red:02X}{green:02X}{blue:02X}"


def rgb_to_lab_array(rgb: np.ndarray) -> np.ndarray:
    rgb_float = rgb.astype(np.float32) / 255.0
    linear = np.where(
        rgb_float <= 0.04045,
        rgb_float / 12.92,
        ((rgb_float + 0.055) / 1.055) ** 2.4,
    )
    xyz = np.empty_like(linear, dtype=np.float32)
    xyz[..., 0] = linear[..., 0] * 0.4124564 + linear[..., 1] * 0.3575761 + linear[..., 2] * 0.1804375
    xyz[..., 1] = linear[..., 0] * 0.2126729 + linear[..., 1] * 0.7151522 + linear[..., 2] * 0.0721750
    xyz[..., 2] = linear[..., 0] * 0.0193339 + linear[..., 1] * 0.1191920 + linear[..., 2] * 0.9503041

    white_point = np.array([0.95047, 1.0, 1.08883], dtype=np.float32)
    normalized_xyz = xyz / white_point
    epsilon = 216 / 24389
    kappa = 24389 / 27
    f_xyz = np.where(
        normalized_xyz > epsilon,
        np.cbrt(normalized_xyz),
        (kappa * normalized_xyz + 16.0) / 116.0,
    )

    lab = np.empty_like(f_xyz, dtype=np.float32)
    lab[..., 0] = 116.0 * f_xyz[..., 1] - 16.0
    lab[..., 1] = 500.0 * (f_xyz[..., 0] - f_xyz[..., 1])
    lab[..., 2] = 200.0 * (f_xyz[..., 1] - f_xyz[..., 2])
    return lab


def delta_e(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    diff = left.astype(np.float32) - right.astype(np.float32)
    return np.sqrt(np.sum(diff * diff, axis=-1))


def is_fill_candidate(rgb: np.ndarray) -> bool:
    red, green, blue = [int(value) for value in rgb]
    max_channel = max(red, green, blue)
    min_channel = min(red, green, blue)
    chroma = max_channel - min_channel
    if max_channel >= 245 and chroma <= 18:
        return False
    if max_channel <= 35:
        return False
    return chroma >= FILL_MIN_CHROMA


def create_fill_candidate_mask(pixels: np.ndarray, shape_mask: np.ndarray) -> np.ndarray:
    max_channel = np.max(pixels, axis=-1)
    min_channel = np.min(pixels, axis=-1)
    chroma = max_channel - min_channel
    not_white_like = ~((max_channel >= 245) & (chroma <= 18))
    not_dark_like = max_channel > 35
    colored_like = chroma >= FILL_MIN_CHROMA
    return shape_mask & not_white_like & not_dark_like & colored_like


def collect_fill_component(
    start_y: int,
    start_x: int,
    candidate_mask: np.ndarray,
    lab_pixels: np.ndarray,
    visited: np.ndarray,
) -> list[tuple[int, int]]:
    height, width = candidate_mask.shape
    queue: deque[tuple[int, int]] = deque([(start_y, start_x)])
    visited[start_y, start_x] = True
    seed_lab = lab_pixels[start_y, start_x].astype(np.float32)
    sum_lab = seed_lab.astype(np.float64)
    mean_lab = seed_lab.astype(np.float64)
    component_pixels: list[tuple[int, int]] = []

    while queue:
        y, x = queue.popleft()
        component_pixels.append((y, x))
        for next_y, next_x in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if not (0 <= next_y < height and 0 <= next_x < width):
                continue
            if not candidate_mask[next_y, next_x] or visited[next_y, next_x]:
                continue
            pixel_lab = lab_pixels[next_y, next_x]
            if float(delta_e(pixel_lab, seed_lab)) > COMPONENT_SEED_DELTA_E:
                continue
            if float(delta_e(pixel_lab, mean_lab)) > COMPONENT_GROW_DELTA_E:
                continue
            visited[next_y, next_x] = True
            queue.append((next_y, next_x))
            sum_lab += pixel_lab
            mean_lab = sum_lab / (len(component_pixels) + len(queue))
    return component_pixels


def component_representative_rgb(component_rgbs: np.ndarray) -> np.ndarray:
    unique_rgbs, counts = np.unique(component_rgbs.reshape(-1, 3), axis=0, return_counts=True)
    return unique_rgbs[int(np.argmax(counts))]


def classify_legend_distances(
    lab: np.ndarray,
    legend_labs: np.ndarray,
    legend_types: list[str],
    legend_hexes: list[str],
) -> dict[str, Any]:
    distances = delta_e(legend_labs, lab)
    ordered = np.argsort(distances)
    best_index = int(ordered[0])
    second_distance = float(distances[ordered[1]]) if len(ordered) > 1 else float("inf")
    return {
        "lab": np.round(lab.astype(np.float32), 3),
        "best_index": best_index,
        "best_distance": float(distances[best_index]),
        "second_distance": second_distance,
        "nearest_land_type": legend_types[best_index],
        "nearest_hex": legend_hexes[best_index],
    }


def nearest_legend_match(rgb: np.ndarray, legend: dict[str, str], tolerance: float) -> dict[str, Any]:
    best_type = None
    best_hex = None
    best_distance = float("inf")
    for land_type, hex_color in legend.items():
        target = np.array(hex_to_rgb(hex_color), dtype=np.int32)
        diff = rgb.astype(np.int32) - target
        distance = sqrt(float(np.sum(diff * diff)))
        if distance < best_distance:
            best_distance = distance
            best_type = land_type
            best_hex = hex_color.upper()
    return {
        "land_type": best_type if best_distance <= tolerance else None,
        "nearest_land_type": best_type,
        "nearest_hex": best_hex,
        "distance": round(best_distance, 3),
        "matched": best_distance <= tolerance,
    }


def nearest_legend_type(rgb: np.ndarray, legend: dict[str, str], tolerance: float) -> str | None:
    return nearest_legend_match(rgb, legend, tolerance)["land_type"]


def should_use_fallback_match(classification: dict[str, Any], pixel_count: int) -> tuple[bool, dict[str, Any]]:
    best_distance = float(classification["best_distance"])
    second_distance = float(classification["second_distance"])
    margin = second_distance - best_distance if second_distance != float("inf") else float("inf")
    ratio = best_distance / second_distance if second_distance not in (0.0, float("inf")) else 0.0
    decision = {
        "best_distance": round(best_distance, 3),
        "second_distance": round(second_distance, 3) if second_distance != float("inf") else None,
        "margin": round(margin, 3) if margin != float("inf") else None,
        "ratio": round(ratio, 4),
        "pixel_count": int(pixel_count),
    }
    if pixel_count < FALLBACK_MATCH_MIN_PIXELS:
        decision["reason"] = "pixel_count_too_small"
        return False, decision
    if best_distance > FALLBACK_MATCH_TOLERANCE:
        decision["reason"] = "distance_too_far"
        return False, decision
    if second_distance != float("inf") and margin < FALLBACK_MATCH_MIN_MARGIN and ratio > FALLBACK_MATCH_MAX_RATIO:
        decision["reason"] = "nearest_category_not_distinct_enough"
        return False, decision
    decision["reason"] = "fallback_match"
    return True, decision


def calculate_land_area(
    image_path: str | Path,
    shape_payload: dict[str, Any],
    legend: dict[str, str],
    meters_per_pixel: float,
    tolerance: float = 35.0,
) -> dict[str, Any]:
    image = Image.open(image_path).convert("RGB")
    pixels = np.asarray(image)
    height, width = pixels.shape[:2]
    shape = Shape(**shape_payload)
    pixel_counts: dict[str, int] = {land_type: 0 for land_type in legend}
    strict_pixel_counts: dict[str, int] = {land_type: 0 for land_type in legend}
    inferred_pixel_counts: dict[str, int] = {land_type: 0 for land_type in legend}
    mask = create_shape_mask(shape, width, height)
    selected_pixels = pixels[mask]
    total_selected = int(selected_pixels.shape[0])
    unmatched = 0
    sampled_colors: Counter[str] = Counter()
    matched_pairs: Counter[tuple[str, str, str]] = Counter()
    inferred_pairs: Counter[tuple[str, str, str]] = Counter()
    unmatched_pairs: Counter[tuple[str, str, str]] = Counter()
    component_summaries: list[dict[str, Any]] = []
    fill_candidate_pixels = 0
    strict_tolerance = max(12.0, tolerance * 0.45)

    if total_selected > 0:
        unique_colors, color_counts = np.unique(selected_pixels.reshape(-1, 3), axis=0, return_counts=True)
        for rgb, count in zip(unique_colors, color_counts, strict=False):
            sampled_colors[rgb_to_hex(rgb)] += int(count)

        legend_items = list(legend.items())
        legend_rgbs = np.array([hex_to_rgb(hex_color) for _, hex_color in legend_items], dtype=np.uint8)
        legend_labs = rgb_to_lab_array(legend_rgbs)
        legend_types = [land_type for land_type, _ in legend_items]
        legend_hexes = [hex_color.upper() for _, hex_color in legend_items]
        lab_pixels = rgb_to_lab_array(pixels)
        candidate_mask = create_fill_candidate_mask(pixels, mask)
        fill_candidate_pixels = int(candidate_mask.sum())
        visited = np.zeros_like(candidate_mask, dtype=bool)
        component_index = 0

        for start_y, start_x in np.argwhere(candidate_mask):
            if visited[start_y, start_x]:
                continue
            component_pixels = collect_fill_component(int(start_y), int(start_x), candidate_mask, lab_pixels, visited)
            if not component_pixels:
                continue

            component_index += 1
            ys = np.fromiter((point[0] for point in component_pixels), dtype=np.int32)
            xs = np.fromiter((point[1] for point in component_pixels), dtype=np.int32)
            component_rgbs = pixels[ys, xs]
            dominant_rgb = component_representative_rgb(component_rgbs)
            dominant_hex = rgb_to_hex(dominant_rgb)
            dominant_lab = rgb_to_lab_array(dominant_rgb.reshape(1, 3))[0]
            component_size = int(len(component_pixels))
            classification = classify_legend_distances(dominant_lab, legend_labs, legend_types, legend_hexes)
            nearest_land_type = classification["nearest_land_type"]
            nearest_hex = classification["nearest_hex"]
            best_distance = classification["best_distance"]
            fallback_used = False

            if best_distance <= strict_tolerance:
                pixel_counts[nearest_land_type] += component_size
                strict_pixel_counts[nearest_land_type] += component_size
                matched_pairs[(dominant_hex, str(nearest_land_type), nearest_hex)] += component_size
            else:
                use_fallback, fallback_decision = should_use_fallback_match(classification, component_size)
                if use_fallback:
                    fallback_used = True
                    pixel_counts[nearest_land_type] += component_size
                    inferred_pixel_counts[nearest_land_type] += component_size
                    inferred_pairs[(dominant_hex, str(nearest_land_type), nearest_hex)] += component_size
                else:
                    unmatched += component_size
                    unmatched_pairs[(dominant_hex, str(nearest_land_type), nearest_hex)] += component_size

            if len(component_summaries) < 20:
                component_summaries.append(
                    {
                        "component_index": component_index,
                        "pixels": component_size,
                        "dominant_color": dominant_hex,
                        "nearest_land_type": nearest_land_type,
                        "nearest_legend_color": nearest_hex,
                        "best_distance": round(float(best_distance), 3),
                        "matched": best_distance <= strict_tolerance or fallback_used,
                        "match_mode": "strict" if best_distance <= strict_tolerance else ("inferred" if fallback_used else "unmatched"),
                        "bbox": {
                            "x1": int(xs.min()),
                            "y1": int(ys.min()),
                            "x2": int(xs.max()),
                            "y2": int(ys.max()),
                        },
                    }
                )

        classified_pixels = sum(pixel_counts.values()) + unmatched
        if classified_pixels < total_selected:
            unmatched += total_selected - classified_pixels

    square_meters_per_pixel = meters_per_pixel * meters_per_pixel
    matched_pixels = sum(pixel_counts.values())
    min_visible_pixels = matched_pixels * MIN_VISIBLE_MATCH_RATIO if matched_pixels > 0 else 0
    ignored_pixel_counts = {
        land_type: count
        for land_type, count in pixel_counts.items()
        if 0 < count < min_visible_pixels and count <= MAX_NOISE_PIXELS
    }
    visible_pixel_counts = {
        land_type: count
        for land_type, count in pixel_counts.items()
        if count > 0 and not (count < min_visible_pixels and count <= MAX_NOISE_PIXELS)
    }
    ignored_pixels = sum(ignored_pixel_counts.values())
    visible_matched_pixels = sum(visible_pixel_counts.values())
    areas = {
        land_type: {
            "pixels": count,
            "square_meters": round(count * square_meters_per_pixel, 2),
            "hectares": round(count * square_meters_per_pixel / 10000, 4),
        }
        for land_type, count in visible_pixel_counts.items()
        if count > 0
    }
    matched_square_meters = round(matched_pixels * square_meters_per_pixel, 2)
    visible_matched_square_meters = round(visible_matched_pixels * square_meters_per_pixel, 2)
    ignored_square_meters = round(ignored_pixels * square_meters_per_pixel, 2)
    unmatched_square_meters = round(unmatched * square_meters_per_pixel, 2)
    total_square_meters = round(total_selected * square_meters_per_pixel, 2)
    debug_payload = {
        "algorithm": "connected_fill_components_lab_matching",
        "image_path": str(image_path),
        "shape": shape_payload,
        "shape_center_color": _sample_shape_center_color(pixels, shape_payload),
        "meters_per_pixel": meters_per_pixel,
        "tolerance": tolerance,
        "strict_delta_e_tolerance": strict_tolerance,
        "total_selected_pixels": total_selected,
        "fill_candidate_pixels": fill_candidate_pixels,
        "non_fill_pixels": total_selected - fill_candidate_pixels,
        "min_visible_match_ratio": MIN_VISIBLE_MATCH_RATIO,
        "max_noise_pixels": MAX_NOISE_PIXELS,
        "component_min_pixels": COMPONENT_MIN_PIXELS,
        "component_seed_delta_e": COMPONENT_SEED_DELTA_E,
        "component_grow_delta_e": COMPONENT_GROW_DELTA_E,
        "fallback_match_tolerance": FALLBACK_MATCH_TOLERANCE,
        "fallback_match_min_margin": FALLBACK_MATCH_MIN_MARGIN,
        "fallback_match_max_ratio": FALLBACK_MATCH_MAX_RATIO,
        "fallback_match_min_pixels": FALLBACK_MATCH_MIN_PIXELS,
        "min_visible_pixels": round(min_visible_pixels, 3),
        "unmatched_pixels": unmatched,
        "top_selected_colors": sampled_colors.most_common(20),
        "component_summaries": component_summaries,
        "top_matched_pairs": [
            {
                "selected_color": selected_hex,
                "matched_land_type": land_type,
                "matched_legend_color": legend_hex,
                "count": count,
            }
            for (selected_hex, land_type, legend_hex), count in matched_pairs.most_common(20)
        ],
        "top_unmatched_nearest_pairs": [
            {
                "selected_color": selected_hex,
                "nearest_land_type": land_type,
                "nearest_legend_color": legend_hex,
                "count": count,
            }
            for (selected_hex, land_type, legend_hex), count in unmatched_pairs.most_common(20)
        ],
        "top_inferred_pairs": [
            {
                "selected_color": selected_hex,
                "inferred_land_type": land_type,
                "inferred_legend_color": legend_hex,
                "count": count,
            }
            for (selected_hex, land_type, legend_hex), count in inferred_pairs.most_common(20)
        ],
        "area_pixels_by_type": {land_type: count for land_type, count in pixel_counts.items() if count > 0},
        "strict_area_pixels_by_type": {land_type: count for land_type, count in strict_pixel_counts.items() if count > 0},
        "inferred_area_pixels_by_type": {land_type: count for land_type, count in inferred_pixel_counts.items() if count > 0},
        "ignored_area_pixels_by_type": ignored_pixel_counts,
        "visible_area_pixels_by_type": visible_pixel_counts,
        "summary": {
            "matched_pixels": matched_pixels,
            "matched_square_meters": matched_square_meters,
            "strict_matched_pixels": sum(strict_pixel_counts.values()),
            "strict_matched_square_meters": round(sum(strict_pixel_counts.values()) * square_meters_per_pixel, 2),
            "inferred_pixels": sum(inferred_pixel_counts.values()),
            "inferred_square_meters": round(sum(inferred_pixel_counts.values()) * square_meters_per_pixel, 2),
            "visible_matched_pixels": visible_matched_pixels,
            "visible_matched_square_meters": visible_matched_square_meters,
            "ignored_pixels": ignored_pixels,
            "ignored_square_meters": ignored_square_meters,
            "unmatched_square_meters": unmatched_square_meters,
            "total_square_meters": total_square_meters,
            "pixel_balance_ok": matched_pixels + unmatched == total_selected,
        },
    }
    debug_snapshot_path = write_area_debug_snapshot(debug_payload)
    if debug_snapshot_path is not None:
        debug_payload["debug_snapshot_path"] = debug_snapshot_path
    print("[area_debug] selected color and legend matching summary:", debug_payload, flush=True)
    return {
        "shape": shape_payload,
        "meters_per_pixel": meters_per_pixel,
        "tolerance": tolerance,
        "strict_delta_e_tolerance": strict_tolerance,
        "total_selected_pixels": total_selected,
        "fill_candidate_pixels": fill_candidate_pixels,
        "unmatched_pixels": unmatched,
        "summary": {
            "matched_pixels": matched_pixels,
            "matched_square_meters": matched_square_meters,
            "matched_hectares": round(matched_square_meters / 10000, 4),
            "strict_matched_pixels": sum(strict_pixel_counts.values()),
            "strict_matched_square_meters": round(sum(strict_pixel_counts.values()) * square_meters_per_pixel, 2),
            "strict_matched_hectares": round(sum(strict_pixel_counts.values()) * square_meters_per_pixel / 10000, 4),
            "inferred_pixels": sum(inferred_pixel_counts.values()),
            "inferred_square_meters": round(sum(inferred_pixel_counts.values()) * square_meters_per_pixel, 2),
            "inferred_hectares": round(sum(inferred_pixel_counts.values()) * square_meters_per_pixel / 10000, 4),
            "visible_matched_pixels": visible_matched_pixels,
            "visible_matched_square_meters": visible_matched_square_meters,
            "visible_matched_hectares": round(visible_matched_square_meters / 10000, 4),
            "ignored_pixels": ignored_pixels,
            "ignored_square_meters": ignored_square_meters,
            "ignored_hectares": round(ignored_square_meters / 10000, 4),
            "unmatched_square_meters": unmatched_square_meters,
            "unmatched_hectares": round(unmatched_square_meters / 10000, 4),
            "total_square_meters": total_square_meters,
            "total_hectares": round(total_square_meters / 10000, 4),
            "matched_ratio": round(matched_pixels / total_selected, 4) if total_selected else 0.0,
            "unmatched_ratio": round(unmatched / total_selected, 4) if total_selected else 0.0,
            "pixel_balance_ok": matched_pixels + unmatched == total_selected,
            "fill_candidate_ratio": round(fill_candidate_pixels / total_selected, 4) if total_selected else 0.0,
            "min_visible_match_ratio": MIN_VISIBLE_MATCH_RATIO,
            "max_noise_pixels": MAX_NOISE_PIXELS,
            "component_min_pixels": COMPONENT_MIN_PIXELS,
            "component_seed_delta_e": COMPONENT_SEED_DELTA_E,
            "component_grow_delta_e": COMPONENT_GROW_DELTA_E,
            "fallback_match_tolerance": FALLBACK_MATCH_TOLERANCE,
            "fallback_match_min_margin": FALLBACK_MATCH_MIN_MARGIN,
            "fallback_match_max_ratio": FALLBACK_MATCH_MAX_RATIO,
            "fallback_match_min_pixels": FALLBACK_MATCH_MIN_PIXELS,
        },
        "areas": areas,
        "strict_area_pixels_by_type": {land_type: count for land_type, count in strict_pixel_counts.items() if count > 0},
        "inferred_area_pixels_by_type": {land_type: count for land_type, count in inferred_pixel_counts.items() if count > 0},
        "component_summaries": component_summaries,
        "debug_snapshot_path": debug_snapshot_path,
    }


def _sample_shape_center_color(pixels: np.ndarray, shape_payload: dict[str, Any]) -> dict[str, Any] | None:
    height, width = pixels.shape[:2]
    if shape_payload.get("type") == "circle":
        center = shape_payload.get("center") or {}
        x = int(round(float(center.get("x", 0))))
        y = int(round(float(center.get("y", 0))))
    elif shape_payload.get("type") == "polygon":
        points = shape_payload.get("points") or []
        if not points:
            return None
        x = int(round(sum(float(point["x"]) for point in points) / len(points)))
        y = int(round(sum(float(point["y"]) for point in points) / len(points)))
    else:
        return None
    if not (0 <= x < width and 0 <= y < height):
        return {"x": x, "y": y, "in_bounds": False}
    return {"x": x, "y": y, "in_bounds": True, "color": rgb_to_hex(pixels[y, x])}


def write_area_debug_snapshot(debug_payload: dict[str, Any]) -> str | None:
    try:
        AREA_DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        latest_path = AREA_DEBUG_DIR / "last_area_debug.json"
        latest_path.write_text(json.dumps(debug_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(latest_path)
    except Exception as error:
        print(f"[area_debug] failed to write debug snapshot: {error}", flush=True)
        return None
