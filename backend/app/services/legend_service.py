from __future__ import annotations

from math import ceil
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageColor


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int] | None:
    try:
        return ImageColor.getrgb(hex_color.strip())[:3]
    except Exception:
        return None


def _rgb_to_hex(rgb: tuple[int, int, int] | np.ndarray) -> str:
    red, green, blue = [int(value) for value in rgb]
    return f"#{red:02X}{green:02X}{blue:02X}"


def _color_distance(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    diff = left.astype(np.int32) - right.astype(np.int32)
    return np.sqrt(np.sum(diff * diff, axis=-1))


def _is_white_like(rgb: np.ndarray) -> np.ndarray:
    return (rgb[:, :, 0] >= 238) & (rgb[:, :, 1] >= 238) & (rgb[:, :, 2] >= 238)


def _is_colored_like(rgb: np.ndarray) -> np.ndarray:
    max_channel = np.max(rgb, axis=-1)
    min_channel = np.min(rgb, axis=-1)
    return (~_is_white_like(rgb)) & (max_channel - min_channel >= 24) & (max_channel >= 90)


def _collect_connected_component(mask: np.ndarray, start_y: int, start_x: int, visited: np.ndarray) -> list[tuple[int, int]]:
    height, width = mask.shape
    stack = [(start_y, start_x)]
    visited[start_y, start_x] = True
    pixels: list[tuple[int, int]] = []
    while stack:
        y, x = stack.pop()
        pixels.append((y, x))
        for next_y, next_x in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if 0 <= next_y < height and 0 <= next_x < width and mask[next_y, next_x] and not visited[next_y, next_x]:
                visited[next_y, next_x] = True
                stack.append((next_y, next_x))
    return pixels


def _group_centers(values: list[float], tolerance: float) -> list[list[float]]:
    groups: list[list[float]] = []
    for value in sorted(values):
        if not groups or abs(np.mean(groups[-1]) - value) > tolerance:
            groups.append([value])
        else:
            groups[-1].append(value)
    return groups


def _dominant_box_color(box_pixels: np.ndarray) -> tuple[int, int, int] | None:
    if box_pixels.size == 0:
        return None
    flat = box_pixels.reshape(-1, 3)
    non_white_mask = ~((flat[:, 0] >= 245) & (flat[:, 1] >= 245) & (flat[:, 2] >= 245))
    filtered = flat[non_white_mask]
    if filtered.size == 0:
        filtered = flat
    unique_colors, counts = np.unique(filtered, axis=0, return_counts=True)
    if unique_colors.size == 0:
        return None
    return tuple(int(value) for value in unique_colors[int(np.argmax(counts))])


def detect_legend_panel_bbox(pixels: np.ndarray) -> dict[str, int] | None:
    height, width = pixels.shape[:2]
    crop_top = int(height * 0.42)
    crop_left = int(width * 0.42)
    cropped = pixels[crop_top:, crop_left:]
    white_mask = _is_white_like(cropped)
    visited = np.zeros(white_mask.shape, dtype=bool)
    candidates: list[dict[str, Any]] = []
    min_width = int(width * 0.18)
    min_height = int(height * 0.12)

    for y in range(white_mask.shape[0]):
        for x in range(white_mask.shape[1]):
            if not white_mask[y, x] or visited[y, x]:
                continue
            component_pixels = _collect_connected_component(white_mask, y, x, visited)
            ys = np.fromiter((point[0] for point in component_pixels), dtype=np.int32)
            xs = np.fromiter((point[1] for point in component_pixels), dtype=np.int32)
            y1 = int(ys.min())
            y2 = int(ys.max())
            x1 = int(xs.min())
            x2 = int(xs.max())
            box_width = x2 - x1 + 1
            box_height = y2 - y1 + 1
            if box_width < min_width or box_height < min_height:
                continue
            touches_edge = x1 == 0 or y1 == 0 or x2 == white_mask.shape[1] - 1 or y2 == white_mask.shape[0] - 1
            if touches_edge:
                continue
            region = cropped[y1 : y2 + 1, x1 : x2 + 1]
            non_white_ratio = 1.0 - float(_is_white_like(region).mean())
            if not (0.03 <= non_white_ratio <= 0.35):
                continue
            candidates.append(
                {
                    "bbox": {"x1": x1 + crop_left, "y1": y1 + crop_top, "x2": x2 + crop_left, "y2": y2 + crop_top},
                    "area": int(len(component_pixels)),
                    "non_white_ratio": round(non_white_ratio, 4),
                }
            )

    if not candidates:
        return None
    candidates.sort(key=lambda item: item["area"], reverse=True)
    return candidates[0]["bbox"]


def detect_legend_grid_swatches(image_path: str | Path, expected_count: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    image = Image.open(image_path).convert("RGB")
    pixels = np.asarray(image)
    panel_bbox = detect_legend_panel_bbox(pixels)
    if panel_bbox is None:
        return [], {"status": "legend_panel_not_found"}

    x1 = panel_bbox["x1"]
    y1 = panel_bbox["y1"]
    x2 = panel_bbox["x2"]
    y2 = panel_bbox["y2"]
    panel = pixels[y1 : y2 + 1, x1 : x2 + 1]
    white_mask = _is_white_like(panel)
    candidate_mask = ~white_mask
    visited = np.zeros(candidate_mask.shape, dtype=bool)
    raw_swatches: list[dict[str, Any]] = []
    panel_height, panel_width = candidate_mask.shape
    min_width = max(20, int(panel_width * 0.06))
    max_width = max(min_width + 1, int(panel_width * 0.14))
    min_height = max(18, int(panel_height * 0.035))
    max_height = max(min_height + 1, int(panel_height * 0.08))
    min_area = max(300, int(panel_width * panel_height * 0.003))

    for row in range(panel_height):
        for col in range(panel_width):
            if not candidate_mask[row, col] or visited[row, col]:
                continue
            component_pixels = _collect_connected_component(candidate_mask, row, col, visited)
            area = len(component_pixels)
            if area < min_area:
                continue
            ys = np.fromiter((point[0] for point in component_pixels), dtype=np.int32)
            xs = np.fromiter((point[1] for point in component_pixels), dtype=np.int32)
            local_y1 = int(ys.min())
            local_y2 = int(ys.max())
            local_x1 = int(xs.min())
            local_x2 = int(xs.max())
            box_width = local_x2 - local_x1 + 1
            box_height = local_y2 - local_y1 + 1
            if box_width < min_width or box_width > max_width or box_height < min_height or box_height > max_height:
                continue
            fill_ratio = area / float(box_width * box_height)
            if fill_ratio < 0.82:
                continue
            sample_pad_x = max(6, int(box_width * 0.2))
            sample_pad_y = max(6, int(box_height * 0.2))
            sample = panel[
                local_y1 + sample_pad_y : max(local_y1 + sample_pad_y + 1, local_y2 - sample_pad_y + 1),
                local_x1 + sample_pad_x : max(local_x1 + sample_pad_x + 1, local_x2 - sample_pad_x + 1),
            ]
            dominant_rgb = _dominant_box_color(sample)
            if dominant_rgb is None:
                continue
            raw_swatches.append(
                {
                    "bbox": {"x1": local_x1 + x1, "y1": local_y1 + y1, "x2": local_x2 + x1, "y2": local_y2 + y1},
                    "center_x": round((local_x1 + local_x2) / 2 + x1, 3),
                    "center_y": round((local_y1 + local_y2) / 2 + y1, 3),
                    "width": box_width,
                    "height": box_height,
                    "area": area,
                    "color": _rgb_to_hex(dominant_rgb),
                    "rgb": dominant_rgb,
                }
            )

    if not raw_swatches:
        return [], {"status": "legend_swatches_not_found", "panel_bbox": panel_bbox}

    widths = np.array([item["width"] for item in raw_swatches], dtype=np.float32)
    heights = np.array([item["height"] for item in raw_swatches], dtype=np.float32)
    x_groups = _group_centers([float(item["center_x"]) for item in raw_swatches], tolerance=max(24.0, float(np.median(widths)) * 1.6))
    y_groups = _group_centers([float(item["center_y"]) for item in raw_swatches], tolerance=max(18.0, float(np.median(heights)) * 0.8))
    column_centers = [float(np.mean(group)) for group in x_groups]
    row_centers = [float(np.mean(group)) for group in y_groups]
    if not column_centers or not row_centers:
        return raw_swatches, {"status": "legend_grid_inference_failed", "panel_bbox": panel_bbox, "raw_swatches": raw_swatches}

    column_count = len(column_centers)
    if expected_count >= 8 and column_count == 1 and len(raw_swatches) >= 6:
        sorted_x = sorted(float(item["center_x"]) for item in raw_swatches)
        spread = sorted_x[-1] - sorted_x[0] if len(sorted_x) > 1 else 0.0
        if spread > float(np.median(widths)) * 2.5:
            midpoint = (sorted_x[0] + sorted_x[-1]) / 2
            column_centers = [float(np.mean([value for value in sorted_x if value <= midpoint])), float(np.mean([value for value in sorted_x if value > midpoint]))]
            column_count = 2
    target_rows = max(1, ceil(expected_count / column_count))

    if len(row_centers) < target_rows:
        if len(row_centers) >= 2:
            step = float(np.median(np.diff(sorted(row_centers))))
        else:
            step = float(np.median(heights) + 40.0)
        while len(row_centers) < target_rows:
            row_centers.append(row_centers[-1] + step)
    row_centers = sorted(row_centers[:target_rows])

    grid_swatches: list[dict[str, Any]] = []
    median_width = int(round(float(np.median(widths))))
    median_height = int(round(float(np.median(heights))))
    for column_index, column_center in enumerate(sorted(column_centers)):
        column_items = [item for item in raw_swatches if abs(float(item["center_x"]) - column_center) <= max(24.0, median_width * 0.9)]
        if column_items:
            column_x1 = int(round(float(np.median([item["bbox"]["x1"] for item in column_items]))))
            column_x2 = int(round(float(np.median([item["bbox"]["x2"] for item in column_items]))))
        else:
            column_x1 = int(round(column_center - median_width / 2))
            column_x2 = int(round(column_center + median_width / 2))

        for row_index, row_center in enumerate(row_centers):
            row_items = [item for item in column_items if abs(float(item["center_y"]) - row_center) <= max(18.0, median_height * 0.8)]
            if row_items:
                source_item = sorted(row_items, key=lambda item: item["area"], reverse=True)[0]
                swatch_bbox = source_item["bbox"]
                color = source_item["color"]
                rgb = source_item["rgb"]
            else:
                swatch_bbox = {
                    "x1": column_x1,
                    "x2": column_x2,
                    "y1": int(round(row_center - median_height / 2)),
                    "y2": int(round(row_center + median_height / 2)),
                }
                sample_pad_x = max(6, int((swatch_bbox["x2"] - swatch_bbox["x1"] + 1) * 0.2))
                sample_pad_y = max(6, int((swatch_bbox["y2"] - swatch_bbox["y1"] + 1) * 0.2))
                sample = pixels[
                    swatch_bbox["y1"] + sample_pad_y : max(swatch_bbox["y1"] + sample_pad_y + 1, swatch_bbox["y2"] - sample_pad_y + 1),
                    swatch_bbox["x1"] + sample_pad_x : max(swatch_bbox["x1"] + sample_pad_x + 1, swatch_bbox["x2"] - sample_pad_x + 1),
                ]
                dominant_rgb = _dominant_box_color(sample)
                if dominant_rgb is None:
                    continue
                color = _rgb_to_hex(dominant_rgb)
                rgb = dominant_rgb
            grid_swatches.append(
                {
                    "column": column_index,
                    "row": row_index,
                    "bbox": swatch_bbox,
                    "color": color,
                    "rgb": rgb,
                }
            )

    grid_swatches.sort(key=lambda item: (item["column"], item["row"]))
    return grid_swatches, {
        "status": "legend_panel_grid",
        "panel_bbox": panel_bbox,
        "raw_swatches": raw_swatches,
        "grid_swatches": grid_swatches,
        "column_count": column_count,
        "row_count": len(row_centers),
    }


def detect_legend_swatches(image_path: str | Path) -> list[dict[str, Any]]:
    image = Image.open(image_path).convert("RGB")
    pixels = np.asarray(image)
    height, width = pixels.shape[:2]
    crop_top = int(height * 0.58)
    cropped = pixels[crop_top:, :]
    colored_mask = _is_colored_like(cropped)
    visited = np.zeros(colored_mask.shape, dtype=bool)
    swatches: list[dict[str, Any]] = []
    min_width = max(18, int(width * 0.012))
    max_width = max(min_width + 1, int(width * 0.11))
    min_height = max(12, int(height * 0.01))
    max_height = max(min_height + 1, int(height * 0.05))
    min_area = max(250, int(width * height * 0.00003))

    for y in range(colored_mask.shape[0]):
        for x in range(colored_mask.shape[1]):
            if not colored_mask[y, x] or visited[y, x]:
                continue
            component_pixels = _collect_connected_component(colored_mask, y, x, visited)
            area = len(component_pixels)
            if area < min_area:
                continue

            ys = np.fromiter((point[0] for point in component_pixels), dtype=np.int32)
            xs = np.fromiter((point[1] for point in component_pixels), dtype=np.int32)
            y1 = int(ys.min())
            y2 = int(ys.max())
            x1 = int(xs.min())
            x2 = int(xs.max())
            box_width = x2 - x1 + 1
            box_height = y2 - y1 + 1
            if box_width < min_width or box_width > max_width or box_height < min_height or box_height > max_height:
                continue

            fill_ratio = area / float(box_width * box_height)
            aspect_ratio = box_width / float(box_height)
            if fill_ratio < 0.45 or not (0.7 <= aspect_ratio <= 4.8):
                continue

            pad_x = max(8, box_width // 2)
            pad_y = max(8, box_height // 2)
            region_x1 = max(0, x1 - pad_x)
            region_x2 = min(cropped.shape[1], x2 + pad_x + 1)
            region_y1 = max(0, y1 - pad_y)
            region_y2 = min(cropped.shape[0], y2 + pad_y + 1)
            neighborhood = cropped[region_y1:region_y2, region_x1:region_x2]
            white_ratio = float(_is_white_like(neighborhood).mean()) if neighborhood.size else 0.0
            if white_ratio < 0.4:
                continue

            box_pixels = cropped[y1 : y2 + 1, x1 : x2 + 1]
            box_mask = colored_mask[y1 : y2 + 1, x1 : x2 + 1]
            component_colors = box_pixels[box_mask]
            if component_colors.size == 0:
                continue
            unique_colors, counts = np.unique(component_colors.reshape(-1, 3), axis=0, return_counts=True)
            order = np.argsort(counts)[::-1]
            dominant_rgb = tuple(int(value) for value in unique_colors[order[0]])
            swatches.append(
                {
                    "bbox": {"x1": x1, "y1": y1 + crop_top, "x2": x2, "y2": y2 + crop_top},
                    "color": _rgb_to_hex(dominant_rgb),
                    "rgb": dominant_rgb,
                    "area": area,
                    "fill_ratio": round(fill_ratio, 4),
                    "white_ratio": round(white_ratio, 4),
                }
            )

    deduped: list[dict[str, Any]] = []
    for swatch in sorted(swatches, key=lambda item: (item["bbox"]["y1"], item["bbox"]["x1"])):
        rgb = np.array(swatch["rgb"], dtype=np.int32)
        if any(np.linalg.norm(rgb - np.array(existing["rgb"], dtype=np.int32)) < 10 for existing in deduped):
            continue
        deduped.append(swatch)
    return deduped


def _build_global_palette(pixels: np.ndarray, bucket_size: int = 4) -> tuple[np.ndarray, np.ndarray]:
    flat_pixels = pixels.reshape(-1, 3)
    quantized = (flat_pixels.astype(np.int32) // bucket_size).clip(0, 63)
    packed = quantized[:, 0] * 4096 + quantized[:, 1] * 64 + quantized[:, 2]
    histogram = np.bincount(packed, minlength=64 * 64 * 64)
    present = np.nonzero(histogram)[0]
    counts = histogram[present]
    colors = np.column_stack(
        ((present // 4096) * bucket_size, ((present // 64) % 64) * bucket_size, (present % 64) * bucket_size)
    ).astype(np.int32)
    return colors, counts


def _best_palette_match(
    target_rgb: tuple[int, int, int],
    palette_colors: np.ndarray,
    palette_counts: np.ndarray,
    *,
    search_radius: float,
    min_pixels: int,
) -> tuple[str | None, dict[str, Any]]:
    target = np.array(target_rgb, dtype=np.int32)
    distance = _color_distance(palette_colors, target)
    candidate_indices = np.where(distance <= search_radius)[0]
    nearby_pixels = int(palette_counts[candidate_indices].sum()) if candidate_indices.size else 0
    ranked_indices = sorted(
        candidate_indices.tolist(),
        key=lambda index: (float(distance[index]), -int(palette_counts[index])),
    )
    if nearby_pixels < min_pixels or not ranked_indices:
        return None, {
            "status": "not_enough_nearby_pixels",
            "nearby_pixels": nearby_pixels,
            "candidate_count": len(ranked_indices),
            "top_candidates": [],
        }

    supported_indices = [index for index in ranked_indices if int(palette_counts[index]) >= min_pixels]
    best_index = supported_indices[0] if supported_indices else ranked_indices[0]
    best_rgb = tuple(int(value) for value in palette_colors[best_index])
    return _rgb_to_hex(best_rgb), {
        "status": "calibrated",
        "matched_pixels": nearby_pixels,
        "dominant_bucket_pixels": int(palette_counts[best_index]),
        "candidate_count": len(ranked_indices),
        "top_candidates": [
            {
                "color": _rgb_to_hex(tuple(int(value) for value in palette_colors[index])),
                "count": int(palette_counts[index]),
                "distance": round(float(distance[index]), 3),
            }
            for index in ranked_indices[:5]
        ],
    }


def calibrate_legend_colors(
    image_path: str | Path,
    legend: dict[str, str],
    search_radius: float = 120.0,
    min_pixels: int = 30,
) -> tuple[dict[str, str], dict[str, Any]]:
    image = Image.open(image_path).convert("RGB")
    pixels = np.asarray(image)
    unique_colors, unique_counts = _build_global_palette(pixels)
    detected_swatches = detect_legend_swatches(image_path)
    panel_grid_swatches, panel_grid_debug = detect_legend_grid_swatches(image_path, len(legend))
    swatch_colors = np.array([swatch["rgb"] for swatch in detected_swatches], dtype=np.int32) if detected_swatches else np.empty((0, 3), dtype=np.int32)
    swatch_counts = np.array([swatch["area"] for swatch in detected_swatches], dtype=np.int32) if detected_swatches else np.empty((0,), dtype=np.int32)
    calibrated: dict[str, str] = {}
    debug: dict[str, Any] = {"detected_swatches": detected_swatches, "panel_grid": panel_grid_debug}

    legend_items = list(legend.items())
    if len(panel_grid_swatches) >= len(legend_items):
        for index, (land_type, llm_hex) in enumerate(legend_items):
            direct_color = str(panel_grid_swatches[index]["color"]).upper()
            calibrated[land_type] = direct_color
            debug[land_type] = {
                "status": "calibrated",
                "llm_color": str(llm_hex).upper(),
                "calibrated_color": direct_color,
                "legend_match_source": "legend_panel_grid",
                "grid_position": {"column": panel_grid_swatches[index]["column"], "row": panel_grid_swatches[index]["row"]},
                "bbox": panel_grid_swatches[index]["bbox"],
            }
        print("[legend_debug] calibrated legend colors:", debug, flush=True)
        return calibrated, debug

    for land_type, llm_hex in legend_items:
        target_rgb = _hex_to_rgb(llm_hex)
        if target_rgb is None:
            calibrated[land_type] = llm_hex
            debug[land_type] = {"status": "invalid_llm_hex", "llm_color": llm_hex}
            continue

        source = "global_palette"
        calibrated_hex = None
        swatch_match_debug: dict[str, Any] | None = None
        if len(detected_swatches) >= max(6, len(legend) // 3):
            calibrated_hex, swatch_match_debug = _best_palette_match(
                target_rgb,
                swatch_colors,
                swatch_counts,
                search_radius=max(search_radius, 140.0),
                min_pixels=1,
            )
            if calibrated_hex is not None:
                source = "legend_swatches"

        global_match_hex, global_match_debug = _best_palette_match(
            target_rgb,
            unique_colors,
            unique_counts,
            search_radius=search_radius,
            min_pixels=min_pixels,
        )
        if calibrated_hex is None:
            calibrated_hex = global_match_hex
            source = "global_palette"

        if calibrated_hex is None:
            calibrated[land_type] = llm_hex.upper()
            debug[land_type] = {
                "status": "not_enough_nearby_pixels",
                "llm_color": llm_hex.upper(),
                "legend_match_source": source,
                "legend_swatches": swatch_match_debug,
                "global_palette": global_match_debug,
            }
            continue

        calibrated[land_type] = calibrated_hex
        debug[land_type] = {
            "status": "calibrated",
            "llm_color": llm_hex.upper(),
            "calibrated_color": calibrated_hex,
            "legend_match_source": source,
            "search_radius": search_radius,
            "min_pixels": min_pixels,
            "legend_swatches": swatch_match_debug,
            "global_palette": global_match_debug,
        }

    print("[legend_debug] calibrated legend colors:", debug, flush=True)
    return calibrated, debug


def summarize_legend_calibration_debug(debug: dict[str, Any]) -> dict[str, Any]:
    panel_grid = debug.get("panel_grid") if isinstance(debug.get("panel_grid"), dict) else {}
    grid_swatches = panel_grid.get("grid_swatches") if isinstance(panel_grid.get("grid_swatches"), list) else []
    summary_method = "global_palette"
    if panel_grid.get("status") == "legend_panel_grid":
        summary_method = "legend_panel_grid"

    legend_items: list[dict[str, Any]] = []
    for key, value in debug.items():
        if key in {"detected_swatches", "panel_grid"} or not isinstance(value, dict):
            continue
        item = {
            "land_type": key,
            "status": value.get("status"),
            "source": value.get("legend_match_source"),
            "llm_color": value.get("llm_color"),
            "calibrated_color": value.get("calibrated_color"),
        }
        if isinstance(value.get("grid_position"), dict):
            item["grid_position"] = {
                "column": int(value["grid_position"].get("column", 0)),
                "row": int(value["grid_position"].get("row", 0)),
            }
        if isinstance(value.get("bbox"), dict):
            item["bbox"] = value["bbox"]
        legend_items.append(item)
        if summary_method != "legend_panel_grid" and value.get("legend_match_source") == "legend_swatches":
            summary_method = "legend_swatches"

    legend_items.sort(
        key=lambda item: (
            0 if "grid_position" in item else 1,
            item.get("grid_position", {}).get("column", 999),
            item.get("grid_position", {}).get("row", 999),
            str(item.get("land_type", "")),
        )
    )

    summary: dict[str, Any] = {
        "method": summary_method,
        "item_count": len(legend_items),
        "matched_item_count": sum(1 for item in legend_items if item.get("status") == "calibrated"),
    }
    result: dict[str, Any] = {"summary": summary, "legend_items": legend_items}

    if panel_grid:
        result["panel_grid"] = {
            "status": panel_grid.get("status"),
            "panel_bbox": panel_grid.get("panel_bbox"),
            "column_count": panel_grid.get("column_count"),
            "row_count": panel_grid.get("row_count"),
            "grid_swatches": [
                {
                    "column": int(swatch.get("column", 0)),
                    "row": int(swatch.get("row", 0)),
                    "color": swatch.get("color"),
                    "bbox": swatch.get("bbox"),
                }
                for swatch in grid_swatches
                if isinstance(swatch, dict)
            ],
        }
        summary["grid_swatch_count"] = len(result["panel_grid"]["grid_swatches"])

    return result
