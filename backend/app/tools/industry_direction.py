from __future__ import annotations

import math
from typing import Any

from sqlalchemy import func, select

from app.core.database import CompanySessionLocal
from app.services.io_service import (
    IoFlowMatrix,
    IoIndustryMapping,
    IoSector,
    _point_in_selection,
    _sector_map,
    get_industry_chain,
)
from app.services.poi_service import query_pois_in_bbox

# How many top sectors to do full chain analysis on
TOP_N_CHAIN = 10

# POI categories relevant to service support scoring
SERVICE_POI_CATEGORIES = [
    "商业服务", "金融保险", "教育", "医疗保健",
    "餐饮", "住宿", "交通运输", "科研服务",
]

# Scoring weights
WEIGHTS = {
    "industry_base": 0.20,
    "industry_linkage": 0.25,
    "chain_completeness": 0.25,
    "agglomeration": 0.15,
    "service_support": 0.15,
}

# Foundation tiers by absolute enterprise count
FOUNDATION_LEVELS: list[tuple[int, str]] = [
    (10, "形成初步集聚"),
    (5, "具备一定基础"),
    (3, "基础较弱"),
    (1, "潜力线索"),
    (0, "无基础"),
]

FOUNDATION_SCORES: dict[str, float] = {
    "形成初步集聚": 1.0,
    "具备一定基础": 0.7,
    "基础较弱": 0.4,
    "潜力线索": 0.15,
    "无基础": 0.0,
}

# Absolute (lo, hi, log?) thresholds for segment normalization per dimension
SEGMENT_THRESHOLDS = {
    "industry_base": (2.0, 20.0, True),
    "industry_linkage": (2.0, 30.0, True),
    "agglomeration": (0.5, 10.0, False),
    "service_support": (10.0, 200.0, False),
}


def _bbox_area_km2(bbox: dict[str, float]) -> float:
    lng_span = bbox["east"] - bbox["west"]
    lat_span = bbox["north"] - bbox["south"]
    mid_lat = (bbox["north"] + bbox["south"]) / 2
    km_per_deg_lng = 111.32 * max(math.cos(math.radians(mid_lat)), 0.01)
    km_per_deg_lat = 110.574
    return lng_span * km_per_deg_lng * lat_span * km_per_deg_lat


def _selection_area_km2(selection: dict[str, Any]) -> float:
    sel_type = selection.get("type")
    if sel_type == "circle":
        r_km = selection.get("radius", 0) / 1000
        return math.pi * r_km * r_km
    if sel_type == "polygon":
        pts = selection.get("points") or []
        if len(pts) < 3:
            return 0.0
        area = 0.0
        n = len(pts)
        for i in range(n):
            j = (i + 1) % n
            area += pts[i].get("x", 0) * pts[j].get("y", 0)
            area -= pts[j].get("x", 0) * pts[i].get("y", 0)
        area = abs(area) / 2.0
        mid_lat = sum(p.get("y", 0) for p in pts) / n
        km_per_deg = 111.32 * max(math.cos(math.radians(mid_lat)), 0.01)
        return area * km_per_deg * 110.574 / km_per_deg
    return 0.0


def _segment_normalize(
    values: list[float],
    *,
    lo: float,
    hi: float,
    log: bool = False,
) -> list[float]:
    """Hybrid normalization: log1p min-max for rich samples, absolute-threshold fallback for small/narrow samples."""
    if not values:
        return []
    if log:
        transformed = [math.log1p(max(v, 0.0)) for v in values]
        lo_t = math.log1p(max(lo, 0.0))
        hi_t = math.log1p(max(hi, 0.0))
    else:
        transformed = list(values)
        lo_t, hi_t = lo, hi

    mn, mx = min(transformed), max(transformed)
    narrow = (mx - mn) <= max(mn * 0.1, 1e-9)
    if len(values) < 3 or narrow:
        rng = max(hi_t - lo_t, 1e-9)
        return [max(0.0, min(1.0, (v - lo_t) / rng)) for v in transformed]
    rng = mx - mn
    return [(v - mn) / rng for v in transformed]


def _classify_foundation(count: int) -> str:
    for threshold, label in FOUNDATION_LEVELS:
        if count >= threshold:
            return label
    return "无基础"


def _classify_recommendation(score: float, foundation: str) -> str:
    solid = foundation in {"形成初步集聚", "具备一定基础"}
    some = foundation in {"形成初步集聚", "具备一定基础", "基础较弱"}
    if score >= 0.70 and solid:
        return "重点推荐"
    if score >= 0.55 and some:
        return "谨慎推荐"
    if score >= 0.40 or foundation == "潜力线索":
        return "潜力观察"
    return "暂不建议"


def _describe_chain(completeness: float) -> str:
    if completeness >= 0.7:
        return "上下游配套较为完整"
    if completeness >= 0.4:
        return "上下游部分覆盖"
    return "产业链存在明显断点"


def _build_reason(
    *,
    same_count: int,
    up_total: int,
    down_total: int,
    completeness: float,
    foundation: str,
) -> str:
    chain_desc = _describe_chain(completeness)
    link_total = up_total + down_total
    if foundation == "形成初步集聚":
        return f"已集聚 {same_count} 家企业，上下游配套 {link_total} 家，{chain_desc}。"
    if foundation == "具备一定基础":
        return f"已有 {same_count} 家企业，上下游配套 {link_total} 家，{chain_desc}，仍有补链空间。"
    if foundation == "基础较弱":
        return f"仅 {same_count} 家企业，但上下游有 {link_total} 家配套，{chain_desc}，可作为培育方向。"
    return f"{same_count} 家企业，上下游 {link_total} 家，{chain_desc}。"


def _batch_count_companies_by_sector(
    db,
    *,
    bbox: dict[str, float] | None,
    selection: dict[str, Any] | None,
) -> dict[int, int]:
    """Count companies in the spatial area, grouped by IO sector ID. Returns {sector_id: count}."""
    from app.models.company import Company

    # Build company_industry -> io_sector_id mapping
    mappings = db.execute(
        select(IoIndustryMapping.company_industry, IoIndustryMapping.io_sector_id)
    ).all()
    ind_to_sector: dict[str, int] = {row[0]: row[1] for row in mappings}
    if not ind_to_sector:
        return {}

    company_industries = list(ind_to_sector.keys())

    stmt = (
        select(Company.industry, func.count(Company.id))
        .where(Company.industry.in_(company_industries))
        .group_by(Company.industry)
    )
    if bbox:
        stmt = stmt.where(
            Company.lng >= bbox["west"],
            Company.lng <= bbox["east"],
            Company.lat >= bbox["south"],
            Company.lat <= bbox["north"],
        )

    if selection:
        # Need individual rows for Python post-filter
        raw_stmt = (
            select(Company.industry, Company.lng, Company.lat)
            .where(Company.industry.in_(company_industries))
        )
        if bbox:
            raw_stmt = raw_stmt.where(
                Company.lng >= bbox["west"],
                Company.lng <= bbox["east"],
                Company.lat >= bbox["south"],
                Company.lat <= bbox["north"],
            )
        raw_rows = db.execute(raw_stmt).all()
        filtered = [r for r in raw_rows if _point_in_selection(r[1], r[2], selection)]
        # Aggregate in Python
        counts: dict[str, int] = {}
        for r in filtered:
            counts[r[0]] = counts.get(r[0], 0) + 1
        sector_counts: dict[int, int] = {}
        for ind_name, cnt in counts.items():
            sid = ind_to_sector.get(ind_name)
            if sid is not None:
                sector_counts[sid] = sector_counts.get(sid, 0) + cnt
        return sector_counts

    rows = db.execute(stmt).all()
    sector_counts: dict[int, int] = {}
    for ind_name, cnt in rows:
        sid = ind_to_sector.get(ind_name)
        if sid is not None:
            sector_counts[sid] = sector_counts.get(sid, 0) + cnt
    return sector_counts


def _count_link_companies(
    db,
    sector_ids: list[int],
    *,
    bbox: dict[str, float] | None,
    selection: dict[str, Any] | None,
) -> dict[int, int]:
    """Count companies for a list of sector IDs in the spatial area."""
    from app.models.company import Company

    if not sector_ids:
        return {}

    # Get company industry names for these sectors
    mappings = db.execute(
        select(IoIndustryMapping.company_industry, IoIndustryMapping.io_sector_id)
        .where(IoIndustryMapping.io_sector_id.in_(sector_ids))
    ).all()

    sid_to_inds: dict[int, list[str]] = {}
    for ind_name, sid in mappings:
        sid_to_inds.setdefault(sid, []).append(ind_name)

    all_industries = []
    for inds in sid_to_inds.values():
        all_industries.extend(inds)

    if not all_industries:
        return {}

    stmt = (
        select(Company.industry, func.count(Company.id))
        .where(Company.industry.in_(all_industries))
        .group_by(Company.industry)
    )
    if bbox:
        stmt = stmt.where(
            Company.lng >= bbox["west"],
            Company.lng <= bbox["east"],
            Company.lat >= bbox["south"],
            Company.lat <= bbox["north"],
        )

    if selection:
        raw_stmt = (
            select(Company.industry, Company.lng, Company.lat)
            .where(Company.industry.in_(all_industries))
        )
        if bbox:
            raw_stmt = raw_stmt.where(
                Company.lng >= bbox["west"],
                Company.lng <= bbox["east"],
                Company.lat >= bbox["south"],
                Company.lat <= bbox["north"],
            )
        raw_rows = db.execute(raw_stmt).all()
        filtered = [r for r in raw_rows if _point_in_selection(r[1], r[2], selection)]
        counts: dict[str, int] = {}
        for r in filtered:
            counts[r[0]] = counts.get(r[0], 0) + 1
        ind_counts = counts
    else:
        rows = db.execute(stmt).all()
        ind_counts = {r[0]: r[1] for r in rows}

    result: dict[int, int] = {}
    for sid, inds in sid_to_inds.items():
        total = sum(ind_counts.get(ind, 0) for ind in inds)
        if total > 0:
            result[sid] = total
    return result


def _count_service_pois(
    db,
    *,
    bbox: dict[str, float] | None,
    selection: dict[str, Any] | None,
) -> int:
    """Count POIs in service-related categories within the area."""
    if not bbox:
        return 0
    items, _ = query_pois_in_bbox(
        db,
        min_lng=bbox["west"],
        min_lat=bbox["south"],
        max_lng=bbox["east"],
        max_lat=bbox["north"],
        categories=SERVICE_POI_CATEGORIES,
        limit=5000,
    )
    if selection:
        items = [p for p in items if _point_in_selection(p.lng, p.lat, selection)]
    return len(items)


async def industry_direction_tool(
    question: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    bbox = context.get("map_bbox") if context else None
    selection = context.get("map_selection") if context else None

    if not bbox and not selection:
        return {
            "status": "no_spatial_range",
            "message": "产业发展方向分析需要地图范围。请在地图上圈选或缩放到目标区域后重试。",
        }

    with CompanySessionLocal() as db:
        # Step 1: batch count all sectors
        sector_counts = _batch_count_companies_by_sector(db, bbox=bbox, selection=selection)

        if not sector_counts:
            return {
                "status": "no_companies",
                "message": "选定区域内未找到企业数据。",
                "area_info": {"area_km2": round(_bbox_area_km2(bbox) if not selection else _selection_area_km2(selection), 2)},
            }

        sectors = _sector_map(db)
        total_companies = sum(sector_counts.values())

        # Step 2: split into seed candidates (>=3 companies) and clue candidates (1-2)
        ranked = sorted(sector_counts.items(), key=lambda x: -x[1])
        seed_pool = [(sid, cnt) for sid, cnt in ranked if cnt >= 3]
        clue_pool = [(sid, cnt) for sid, cnt in ranked if cnt < 3]
        top_n = seed_pool[:TOP_N_CHAIN]

        # Step 3: area
        area_km2 = _selection_area_km2(selection) if selection else _bbox_area_km2(bbox)
        area_km2 = max(area_km2, 0.01)

        # Step 4: POI service count
        poi_count = _count_service_pois(db, bbox=bbox, selection=selection)

        # Step 5: chain analysis + scoring for seed candidates (count >= 3)
        scores: list[dict[str, Any]] = []
        scored_chain_data: list[dict[str, Any]] = []
        no_chain_sector_ids: set[int] = set()

        for sector_id, same_count in top_n:
            sector = sectors.get(sector_id)
            if not sector:
                continue
            chain = get_industry_chain(db, industry=sector.name, top_n=5)
            if chain is None:
                no_chain_sector_ids.add(sector_id)
                continue

            # Count upstream/downstream companies
            up_ids = [_get_sector_id_by_code(db, li.sector_code) for li in chain.upstream]
            down_ids = [_get_sector_id_by_code(db, li.sector_code) for li in chain.downstream]
            up_ids = [i for i in up_ids if i]
            down_ids = [i for i in down_ids if i]

            link_counts = _count_link_companies(db, up_ids + down_ids, bbox=bbox, selection=selection)
            up_total = sum(link_counts.get(sid, 0) for sid in up_ids)
            down_total = sum(link_counts.get(sid, 0) for sid in down_ids)

            # Chain completeness: how many of top-5 upstream + top-5 downstream have companies
            up_present = sum(1 for sid in up_ids if link_counts.get(sid, 0) > 0)
            down_present = sum(1 for sid in down_ids if link_counts.get(sid, 0) > 0)
            total_links = len(up_ids) + len(down_ids)
            present_links = up_present + down_present
            completeness = present_links / total_links if total_links > 0 else 0.0

            scored_chain_data.append({
                "sector": sector,
                "chain": chain,
                "same_count": same_count,
                "up_total": up_total,
                "down_total": down_total,
                "completeness": completeness,
            })

        # Hybrid normalization (log1p min-max with absolute-threshold fallback)
        base_lo, base_hi, base_log = SEGMENT_THRESHOLDS["industry_base"]
        link_lo, link_hi, link_log = SEGMENT_THRESHOLDS["industry_linkage"]
        agg_lo, agg_hi, agg_log = SEGMENT_THRESHOLDS["agglomeration"]
        svc_lo, svc_hi, _ = SEGMENT_THRESHOLDS["service_support"]

        base_norm = _segment_normalize(
            [float(cd["same_count"]) for cd in scored_chain_data],
            lo=base_lo, hi=base_hi, log=base_log,
        )
        linkage_norm = _segment_normalize(
            [float(cd["up_total"] + cd["down_total"]) for cd in scored_chain_data],
            lo=link_lo, hi=link_hi, log=link_log,
        )
        agg_norm = _segment_normalize(
            [cd["same_count"] / area_km2 for cd in scored_chain_data],
            lo=agg_lo, hi=agg_hi, log=agg_log,
        )
        # Service support is a region-level constant: apply absolute threshold
        service_norm = max(0.0, min(1.0, (poi_count - svc_lo) / max(svc_hi - svc_lo, 1e-9)))

        for i, cd in enumerate(scored_chain_data):
            same_count = cd["same_count"]
            sector = cd["sector"]
            chain = cd["chain"]
            up_total = cd["up_total"]
            down_total = cd["down_total"]
            completeness = cd["completeness"]
            agg_value = same_count / area_km2

            bn = base_norm[i] if i < len(base_norm) else 0.0
            ln = linkage_norm[i] if i < len(linkage_norm) else 0.0
            an = agg_norm[i] if i < len(agg_norm) else 0.0
            cn = completeness  # already 0-1, no normalization needed

            foundation = _classify_foundation(same_count)
            # Mixed base dimension: relative magnitude + absolute tier
            base_dim = 0.6 * bn + 0.4 * FOUNDATION_SCORES[foundation]

            composite = (
                WEIGHTS["industry_base"] * base_dim
                + WEIGHTS["industry_linkage"] * ln
                + WEIGHTS["chain_completeness"] * cn
                + WEIGHTS["agglomeration"] * an
                + WEIGHTS["service_support"] * service_norm
            )

            recommendation = _classify_recommendation(composite, foundation)
            reason = _build_reason(
                same_count=same_count,
                up_total=up_total,
                down_total=down_total,
                completeness=completeness,
                foundation=foundation,
            )

            key_up = [li.sector_name for li in chain.upstream[:3]]
            key_down = [li.sector_name for li in chain.downstream[:3]]

            scores.append({
                "rank": 0,
                "industry": sector.name,
                "sector_code": sector.code,
                "sector_name": sector.name,
                "category": sector.category,
                "score": round(composite, 4),
                "composite_score": round(composite, 4),  # alias for backward compat
                "enterprise_count": same_count,
                "same_sector_count": same_count,  # alias
                "foundation_level": foundation,
                "chain_completeness": _describe_chain(completeness),
                "recommendation_level": recommendation,
                "reason": reason,
                "dimensions": {
                    "industry_base": {"raw": same_count, "normalized": round(base_dim, 4)},
                    "industry_linkage": {"raw": up_total + down_total, "normalized": round(ln, 4)},
                    "chain_completeness": {"raw": round(cn, 4), "normalized": round(cn, 4)},
                    "agglomeration": {"raw": round(agg_value, 2), "normalized": round(an, 4)},
                    "service_support": {"raw": poi_count, "normalized": round(service_norm, 4)},
                },
                "upstream_count": up_total,
                "downstream_count": down_total,
                "key_upstream": key_up,
                "key_downstream": key_down,
            })

        # Final sort by composite
        scores.sort(key=lambda x: -x["score"])
        for i, s in enumerate(scores):
            s["rank"] = i + 1

        # Other sectors: count >= 3 but no IO chain available, or beyond Top-N
        top_n_ids = {sid for sid, _ in top_n}
        other_sectors = []
        for sector_id, cnt in ranked:
            if sector_id in top_n_ids and sector_id not in no_chain_sector_ids:
                continue
            if cnt < 3:
                continue  # these go to potential_clues
            sector = sectors.get(sector_id)
            if sector:
                other_sectors.append({"sector_code": sector.code, "sector_name": sector.name, "company_count": cnt})

        # Potential clues: 1-2 companies, sample too small for formal scoring
        potential_clues = []
        for sector_id, cnt in clue_pool:
            sector = sectors.get(sector_id)
            if sector:
                potential_clues.append({
                    "industry": sector.name,
                    "enterprise_count": cnt,
                    "foundation_level": _classify_foundation(cnt),
                    "note": "样本过少，仅作观察",
                })

        # Recommendation buckets
        recommendation_summary: dict[str, list[str]] = {
            "重点推荐": [],
            "谨慎推荐": [],
            "潜力观察": [],
            "暂不建议": [],
        }
        for s in scores:
            recommendation_summary[s["recommendation_level"]].append(s["industry"])

        # Summary
        top3_names = "、".join(s["sector_name"] for s in scores[:3])
        summary = (
            f"区域面积{area_km2:.1f}km²，"
            f"共有企业{total_companies}家，涉及{len(sector_counts)}个产业部门。"
            f"综合评估排名前三的优势产业为{top3_names}。"
            f"区域内服务配套POI共{poi_count}个。"
        )

        return {
            "status": "ok",
            "area_info": {
                "area_km2": round(area_km2, 2),
                "total_companies": total_companies,
                "total_sectors": len(sector_counts),
                "total_pois": poi_count,
            },
            "industry_scores": scores,
            "potential_clues": potential_clues[:30],
            "recommendation_summary": recommendation_summary,
            "other_sectors": other_sectors[:20],
            "summary": summary,
        }


def _get_sector_id_by_code(db, code: str) -> int | None:
    return db.scalar(select(IoSector.id).where(IoSector.code == code))
