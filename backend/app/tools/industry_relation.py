from __future__ import annotations

from typing import Any

from app.core.database import CompanySessionLocal
from app.services.io_service import get_industry_chain, get_local_enterprises, get_related_companies


async def industry_relation_tool(question: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    industry = ""
    if context:
        industry = context.get("industry", "") or context.get("question", "")
    if not industry:
        industry = question

    with CompanySessionLocal() as db:
        chain = get_industry_chain(db, industry=industry, top_n=5)

    if chain is None:
        return {
            "status": "not_found",
            "message": f'未找到与「{industry}」匹配的投入产出表部门。请尝试更具体的产业名称，如汽车制造业、电气机械和器材制造业、软件和信息技术服务业。',
            "industry": industry,
        }

    upstream_sectors = [
        {"sector_code": li.sector_code, "sector_name": li.sector_name, "category": li.category,
         "flow_value": li.flow_value, "flow_value_yi": round(li.flow_value / 10000, 2),
         "coefficient": li.coefficient}
        for li in chain.upstream
    ]
    downstream_sectors = [
        {"sector_code": li.sector_code, "sector_name": li.sector_name, "category": li.category,
         "flow_value": li.flow_value, "flow_value_yi": round(li.flow_value / 10000, 2),
         "coefficient": li.coefficient}
        for li in chain.downstream
    ]

    total_output_yi = round(chain.total_output / 10000, 2) if chain.total_output else None
    total_input_yi = round(chain.total_input / 10000, 2) if chain.total_input else None

    # enterprise statistics
    with CompanySessionLocal() as db:
        io_sector_id = _get_sector_id(db, chain.sector_code)
        upstream_ids = [_get_sector_id(db, li.sector_code) for li in chain.upstream]
        downstream_ids = [_get_sector_id(db, li.sector_code) for li in chain.downstream]

        bbox = context.get("map_bbox") if context else None
        selection = context.get("map_selection") if context else None
        district = context.get("district") if context else None

        local = get_local_enterprises(
            db,
            io_sector_id=io_sector_id,
            upstream_sector_ids=[i for i in upstream_ids if i],
            downstream_sector_ids=[i for i in downstream_ids if i],
            district=district,
            bbox=bbox,
            selection=selection,
        )

        related = get_related_companies(
            db,
            io_sector_id=io_sector_id,
            upstream_sector_ids=[i for i in upstream_ids if i],
            downstream_sector_ids=[i for i in downstream_ids if i],
            district=district,
            bbox=bbox,
            selection=selection,
        )

    same_total = sum(item["count"] for item in local["same_industry"])
    upstream_total = sum(item["count"] for item in local["upstream"])
    downstream_total = sum(item["count"] for item in local["downstream"])

    # Deduplicate related companies by id, priority: target > upstream > downstream
    seen: dict[int, str] = {}
    priority = {"target": 0, "upstream": 1, "downstream": 2}
    for company in related:
        cid = company["id"]
        rel = company["relation"]
        if cid not in seen or priority.get(rel, 3) < priority.get(seen[cid], 3):
            seen[cid] = rel
    deduped_related = [
        next(c for c in related if c["id"] == cid)
        for cid in sorted(seen.keys())
    ]
    # Update relation to reflect priority
    for c in deduped_related:
        c["relation"] = seen[c["id"]]
    total_unique_count = len(deduped_related)

    # Scope description for summary
    if selection:
        scope_desc = "在当前圈选范围内"
    elif bbox:
        scope_desc = "在当前地图视野范围内"
    else:
        scope_desc = "在全库范围内"

    upstream_summary = "、".join(u["sector_name"] for u in upstream_sectors[:3])
    downstream_summary = "、".join(d["sector_name"] for d in downstream_sectors[:3])

    summary = (
        f"{scope_desc}，「{chain.sector_name}」"
        f"同行业企业{same_total}家，上游关联企业{upstream_total}家，下游关联企业{downstream_total}家，"
        f"去重后关联企业共{total_unique_count}家。"
    )

    return {
        "status": "ok",
        "industry": industry,
        "matched_sector": {
            "code": chain.sector_code,
            "name": chain.sector_name,
            "category": chain.category,
            "total_output_yi": total_output_yi,
            "total_input_yi": total_input_yi,
        },
        "upstream": upstream_sectors,
        "downstream": downstream_sectors,
        "local_enterprises": local,
        "related_companies": deduped_related,
        "total_unique_count": total_unique_count,
        "scope": scope_desc,
        "summary": summary,
    }


def _get_sector_id(db, code: str) -> int | None:
    from app.services.io_service import IoSector
    from sqlalchemy import select
    row = db.scalar(select(IoSector.id).where(IoSector.code == code))
    return row
