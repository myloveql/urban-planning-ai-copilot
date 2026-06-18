from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, desc, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.database import Base

# ---------------------------------------------------------------------------
# Inline models (tables created by scripts/init_io_table.py)
# ---------------------------------------------------------------------------


class IoSector(Base):
    __tablename__ = "io_sectors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(4), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[str] = mapped_column(String(4), nullable=False)
    total_output: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_input: Mapped[float | None] = mapped_column(Float, nullable=True)
    intermediate_input_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_added_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    labor_compensation: Mapped[float | None] = mapped_column(Float, nullable=True)
    net_tax_production: Mapped[float | None] = mapped_column(Float, nullable=True)
    fixed_asset_depreciation: Mapped[float | None] = mapped_column(Float, nullable=True)
    operating_surplus: Mapped[float | None] = mapped_column(Float, nullable=True)


class IoFlowMatrix(Base):
    __tablename__ = "io_flow_matrix"
    __table_args__ = (
        UniqueConstraint("row_sector_id", "col_sector_id", name="uq_flow_rc"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    row_sector_id: Mapped[int] = mapped_column(Integer, ForeignKey("io_sectors.id"), nullable=False, index=True)
    col_sector_id: Mapped[int] = mapped_column(Integer, ForeignKey("io_sectors.id"), nullable=False, index=True)
    flow_value: Mapped[float] = mapped_column(Float, nullable=False)
    direct_consumption_coeff: Mapped[float | None] = mapped_column(Float, nullable=True)


class IoIndustryMapping(Base):
    __tablename__ = "io_industry_mapping"
    __table_args__ = (
        Index("ix_io_industry_mapping_company_industry", "company_industry"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_industry: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    io_sector_id: Mapped[int] = mapped_column(Integer, ForeignKey("io_sectors.id"), nullable=False)
    confidence: Mapped[str] = mapped_column(String(8), nullable=False, default="exact")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


# ---------------------------------------------------------------------------
# Alias mapping: common user terms → IO sector code
# ---------------------------------------------------------------------------

_INDUSTRY_ALIASES: dict[str, str] = {
    # 制造业
    "新能源汽车": "18",
    "汽车": "18",
    "汽车制造": "18",
    "汽车产业": "18",
    "汽车零部件": "16",
    "电子信息": "20",
    "电子制造": "20",
    "电子产业": "20",
    "半导体": "20",
    "芯片": "20",
    "集成电路": "20",
    "计算机": "20",
    "手机": "20",
    "智能终端": "20",
    "通信设备": "20",
    "通信产业": "20",
    "化工": "12",
    "化工产业": "12",
    "化学工业": "12",
    "化学原料": "12",
    "塑料": "12",
    "塑料制品": "12",
    "橡胶": "12",
    "橡胶制品": "12",
    "医药": "12",
    "医药制造": "12",
    "制药": "12",
    "生物医药": "12",
    "化学纤维": "12",
    "食品加工": "06",
    "食品": "06",
    "食品制造": "06",
    "食品产业": "06",
    "饮料": "06",
    "酒": "06",
    "烟草": "06",
    "纺织": "07",
    "纺织业": "07",
    "服装": "08",
    "服装制造": "08",
    "皮革": "08",
    "家具": "09",
    "家居": "09",
    "智能家居": "09",
    "木材加工": "09",
    "造纸": "10",
    "印刷": "10",
    "文教用品": "10",
    "石油": "11",
    "炼油": "11",
    "石油化工": "11",
    "燃油": "11",
    "建材": "13",
    "建筑材料": "13",
    "陶瓷": "13",
    "玻璃": "13",
    "水泥": "13",
    "非金属": "13",
    "新材料": "13",
    "钢铁": "14",
    "有色": "14",
    "有色金属": "14",
    "铝型材": "14",
    "铝材": "14",
    "铜材": "14",
    "金属冶炼": "14",
    "金属制品": "15",
    "金属加工": "15",
    "五金": "15",
    "不锈钢": "15",
    "通用设备": "16",
    "装备制造": "16",
    "机械制造": "16",
    "机械": "16",
    "智能制造": "16",
    "机器人": "16",
    "数控机床": "16",
    "专用设备": "17",
    "工程机械": "17",
    "农业机械": "17",
    "电气机械": "19",
    "电气": "19",
    "电气设备": "19",
    "电机": "19",
    "家电": "19",
    "家用电器": "19",
    "电力设备": "19",
    "输变电设备": "19",
    "仪器仪表": "21",
    "传感器": "21",
    "电力": "22",
    "电力供应": "22",
    "新能源": "22",
    "光伏": "22",
    "风电": "22",
    "热力": "22",
    "燃气": "25",
    "自来水": "26",
    # 第三产业
    "建筑": "27",
    "建筑业": "27",
    "建筑工程": "27",
    "土木工程": "27",
    "装饰": "27",
    "装修": "27",
    "房地产": "33",
    "房地产中介": "33",
    "物业": "33",
    "批发零售": "28",
    "商贸": "28",
    "商业": "28",
    "零售": "28",
    "物流": "29",
    "交通运输": "29",
    "运输": "29",
    "仓储": "29",
    "快递": "29",
    "货运": "29",
    "港口": "29",
    "航空": "29",
    "餐饮": "30",
    "住宿": "30",
    "酒店": "30",
    "旅游": "30",
    "文旅": "41",
    "互联网": "31",
    "软件": "31",
    "IT": "31",
    "信息技术": "31",
    "电信": "31",
    "通信": "31",
    "金融": "32",
    "银行": "32",
    "保险": "32",
    "证券": "32",
    "商务服务": "34",
    "现代服务业": "34",
    "专业服务": "34",
    "咨询服务": "34",
    "法律": "34",
    "会计": "34",
    "科技服务": "35",
    "研发": "35",
    "科研": "35",
    "技术服务": "35",
    "水利": "37",
    "环保": "37",
    "环境": "37",
    "生态": "37",
    "公共服务": "37",
    "居民服务": "38",
    "家政": "38",
    "养老": "38",
    "教育": "40",
    "培训": "40",
    "学校": "40",
    "医疗": "41",
    "卫生": "41",
    "医院": "41",
    "文化": "41",
    "娱乐": "41",
    "体育": "41",
    "影视": "41",
    "游戏": "41",
    "公共服务管理": "42",
    "社会保障": "42",
    "农业": "01",
    "种植业": "01",
    "养殖": "01",
    "畜牧业": "01",
    "渔业": "01",
    "林业": "01",
    "农副产品": "01",
    "煤炭": "02",
    "矿产": "04",
    "矿业": "04",
    "采矿": "04",
    "非金属矿": "05",
    "采盐": "05",
}

# Suffixes to strip when extracting industry name from a question
_STRIP_SUFFIXES = re.compile(
    r"(产业链|上下游|产业关联|产业基础|产业集聚|产业集群|产业配套"
    r"|关联产业|行业分析|产业链条|产业发展|行业"
    r"|有哪些|是什么|怎么样|情况|分析|查询|了解|介绍|说明"
    r"|的|了|吗|呢|吧|啊|嘛|请问|帮我|麻烦|一下|看看|查一下|问一下"
    r"|佛山|三水|南海|顺德|禅城|高明|地区|区域|本地)"
)


def _clean_industry_text(text: str) -> str:
    """Strip question noise from an industry query string."""
    text = text.strip()
    # Remove common question prefixes/suffixes to isolate the industry name
    text = _STRIP_SUFFIXES.sub("", text).strip()
    return text


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

DEFAULT_TOP_N = 5


@dataclass(frozen=True)
class LinkedIndustry:
    """A single linked industry with flow details."""

    sector_code: str
    sector_name: str
    category: str
    flow_value: float
    coefficient: float | None


@dataclass(frozen=True)
class IndustryChain:
    """Complete upstream + downstream chain for a sector."""

    sector_code: str
    sector_name: str
    category: str
    total_output: float | None
    total_input: float | None
    upstream: list[LinkedIndustry]
    downstream: list[LinkedIndustry]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_sector(db: Session, industry: str) -> IoSector | None:
    """Resolve a company industry name or IO sector code/name to an IoSector row."""
    text = industry.strip()
    if not text:
        return None

    # direct code match
    sector = db.scalar(select(IoSector).where(IoSector.code == text))
    if sector:
        return sector

    # direct name match
    sector = db.scalar(select(IoSector).where(IoSector.name == text))
    if sector:
        return sector

    # industry mapping lookup
    mapping = db.scalar(
        select(IoIndustryMapping).where(IoIndustryMapping.company_industry == text)
    )
    if mapping:
        return db.get(IoSector, mapping.io_sector_id)

    # alias lookup (after stripping question noise)
    cleaned = _clean_industry_text(text)
    if cleaned and cleaned != text:
        # try cleaned text against code, name, mapping
        sector = db.scalar(select(IoSector).where(IoSector.code == cleaned))
        if sector:
            return sector
        sector = db.scalar(select(IoSector).where(IoSector.name == cleaned))
        if sector:
            return sector
        mapping = db.scalar(
            select(IoIndustryMapping).where(IoIndustryMapping.company_industry == cleaned)
        )
        if mapping:
            return db.get(IoSector, mapping.io_sector_id)

    # alias dictionary
    alias_code = _INDUSTRY_ALIASES.get(cleaned or text)
    if alias_code:
        sector = db.scalar(select(IoSector).where(IoSector.code == alias_code))
        if sector:
            return sector

    # try each word segment against alias
    for segment in _split_industry_segments(cleaned or text):
        alias_code = _INDUSTRY_ALIASES.get(segment)
        if alias_code:
            sector = db.scalar(select(IoSector).where(IoSector.code == alias_code))
            if sector:
                return sector

    # fuzzy name match
    for candidate in (text, cleaned) if cleaned != text else (text,):
        sector = db.scalar(
            select(IoSector).where(IoSector.name.ilike(f"%{candidate}%")).limit(1)
        )
        if sector:
            return sector

    return None


def _split_industry_segments(text: str) -> list[str]:
    """Split '新能源汽车制造' into ['新能源汽车', '汽车制造', '新能源汽车制造']."""
    segments: list[str] = []
    # try decreasing lengths
    for length in range(len(text), 1, -1):
        for start in range(len(text) - length + 1):
            seg = text[start:start + length]
            if seg not in segments:
                segments.append(seg)
    return segments


def _sector_map(db: Session) -> dict[int, IoSector]:
    rows = db.scalars(select(IoSector)).all()
    return {s.id: s for s in rows}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_upstream_industries(
    db: Session,
    *,
    industry: str,
    top_n: int = DEFAULT_TOP_N,
) -> list[LinkedIndustry]:
    """Return the top-N upstream industries for a given industry.

    Upstream = suppliers: sectors whose products flow *into* the target sector.
    In the IO matrix this is the target's column: row_sector → col_sector(target).
    """
    sector = _resolve_sector(db, industry)
    if sector is None:
        return []

    sectors = _sector_map(db)

    rows = db.execute(
        select(IoFlowMatrix)
        .where(IoFlowMatrix.col_sector_id == sector.id, IoFlowMatrix.row_sector_id != sector.id)
        .order_by(desc(IoFlowMatrix.flow_value))
        .limit(top_n)
    ).scalars().all()

    results: list[LinkedIndustry] = []
    for r in rows:
        s = sectors.get(r.row_sector_id)
        if s is None:
            continue
        results.append(LinkedIndustry(
            sector_code=s.code,
            sector_name=s.name,
            category=s.category,
            flow_value=r.flow_value,
            coefficient=r.direct_consumption_coeff,
        ))
    return results


def get_downstream_industries(
    db: Session,
    *,
    industry: str,
    top_n: int = DEFAULT_TOP_N,
) -> list[LinkedIndustry]:
    """Return the top-N downstream industries for a given industry.

    Downstream = consumers: sectors that use the target sector's products.
    In the IO matrix this is the target's row: row_sector(target) → col_sector.
    """
    sector = _resolve_sector(db, industry)
    if sector is None:
        return []

    sectors = _sector_map(db)

    rows = db.execute(
        select(IoFlowMatrix)
        .where(IoFlowMatrix.row_sector_id == sector.id, IoFlowMatrix.col_sector_id != sector.id)
        .order_by(desc(IoFlowMatrix.flow_value))
        .limit(top_n)
    ).scalars().all()

    results: list[LinkedIndustry] = []
    for r in rows:
        s = sectors.get(r.col_sector_id)
        if s is None:
            continue
        results.append(LinkedIndustry(
            sector_code=s.code,
            sector_name=s.name,
            category=s.category,
            flow_value=r.flow_value,
            coefficient=r.direct_consumption_coeff,
        ))
    return results


def get_industry_chain(
    db: Session,
    *,
    industry: str,
    top_n: int = DEFAULT_TOP_N,
) -> IndustryChain | None:
    """Return the full industry chain (upstream + downstream) for a given industry."""
    sector = _resolve_sector(db, industry)
    if sector is None:
        return None

    upstream = get_upstream_industries(db, industry=sector.name, top_n=top_n)
    downstream = get_downstream_industries(db, industry=sector.name, top_n=top_n)

    return IndustryChain(
        sector_code=sector.code,
        sector_name=sector.name,
        category=sector.category,
        total_output=sector.total_output,
        total_input=sector.total_input,
        upstream=upstream,
        downstream=downstream,
    )


def get_local_enterprises(
    db: Session,
    *,
    io_sector_id: int,
    upstream_sector_ids: list[int],
    downstream_sector_ids: list[int],
    district: str | None = None,
    bbox: dict[str, float] | None = None,
    selection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Count local enterprises for a sector, its upstream and downstream chains.

    Returns a dict with same_industry, upstream, and downstream enterprise counts.
    """
    from app.models.company import Company

    all_sector_ids = [io_sector_id] + upstream_sector_ids + downstream_sector_ids
    if not all_sector_ids:
        return {"same_industry": [], "upstream": [], "downstream": []}

    # sector id → name mapping
    sectors = _sector_map(db)

    # io_sector_id → list of company industry names via mapping table
    sector_to_company_industries: dict[int, list[str]] = {}
    for sid in set(all_sector_ids):
        mappings = db.scalars(
            select(IoIndustryMapping.company_industry).where(IoIndustryMapping.io_sector_id == sid)
        ).all()
        sector_to_company_industries[sid] = list(mappings)

    def _count_enterprises(industries: list[str]) -> list[dict[str, Any]]:
        if not industries:
            return []
        if selection:
            # Must fetch individual rows for Python post-filter
            raw_stmt = (
                select(Company.id, Company.industry, Company.lng, Company.lat)
                .where(Company.industry.in_(industries))
            )
            if district:
                raw_stmt = raw_stmt.where(Company.district.ilike(f"%{district}%"))
            if bbox:
                raw_stmt = raw_stmt.where(
                    Company.lng >= bbox["west"],
                    Company.lng <= bbox["east"],
                    Company.lat >= bbox["south"],
                    Company.lat <= bbox["north"],
                )
            raw_rows = db.execute(raw_stmt).all()
            filtered = [r for r in raw_rows if _point_in_selection(r[2], r[3], selection)]
            # Aggregate in Python
            ind_counts: dict[str, int] = {}
            for r in filtered:
                ind_name = r[1]
                if ind_name:
                    ind_counts[ind_name] = ind_counts.get(ind_name, 0) + 1
            results: list[dict[str, Any]] = []
            for ind_name, count in sorted(ind_counts.items(), key=lambda x: -x[1]):
                results.append({"industry_name": ind_name, "count": count})
            return results
        stmt = (
            select(Company.industry, func.count(Company.id), func.sum(Company.registered_capital))
            .where(Company.industry.in_(industries))
            .group_by(Company.industry)
            .order_by(func.count(Company.id).desc())
        )
        if district:
            stmt = stmt.where(Company.district.ilike(f"%{district}%"))
        if bbox:
            stmt = stmt.where(
                Company.lng >= bbox["west"],
                Company.lng <= bbox["east"],
                Company.lat >= bbox["south"],
                Company.lat <= bbox["north"],
            )
        rows = db.execute(stmt).all()
        results2: list[dict[str, Any]] = []
        for ind_name, count, cap_sum in rows:
            if not ind_name:
                continue
            results2.append({
                "industry_name": ind_name,
                "count": count,
                "registered_capital_sum": _clean_capital(cap_sum),
            })
        return results2

    def _aggregate(group_sector_ids: list[int]) -> list[dict[str, Any]]:
        all_industries: list[str] = []
        for sid in group_sector_ids:
            all_industries.extend(sector_to_company_industries.get(sid, []))
        return _count_enterprises(all_industries)

    same = _count_enterprises(sector_to_company_industries.get(io_sector_id, []))
    upstream = _aggregate(upstream_sector_ids)
    downstream = _aggregate(downstream_sector_ids)

    return {
        "same_industry": same,
        "upstream": upstream,
        "downstream": downstream,
    }


def _clean_capital(value: str | float | None) -> str | None:
    """Extract numeric value from capital string like '5000万人民币'."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return f"{value:.0f}"
    value = str(value)
    m = re.search(r"[\d.]+", value)
    if m:
        return m.group() + "万" if "万" in value else m.group()
    return value


def _point_in_polygon(lng: float, lat: float, polygon: list[tuple[float, float]]) -> bool:
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > lat) != (yj > lat)) and (lng < (xj - xi) * (lat - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def _point_in_circle(lng: float, lat: float, cx: float, cy: float, radius_m: float) -> bool:
    dx = (lng - cx) * 111320 * max(math.cos(math.radians(cy)), 0.01)
    dy = (lat - cy) * 111320
    return (dx * dx + dy * dy) <= (radius_m * radius_m)


def _point_in_selection(lng: float, lat: float, selection: dict[str, Any]) -> bool:
    sel_type = selection.get("type")
    if sel_type == "circle":
        center = selection.get("center") or {}
        return _point_in_circle(lng, lat, center.get("x", 0), center.get("y", 0), selection.get("radius", 0))
    if sel_type == "polygon":
        points = selection.get("points") or []
        return _point_in_polygon(lng, lat, [(p.get("x", 0), p.get("y", 0)) for p in points])
    return True


def get_related_companies(
    db: Session,
    *,
    io_sector_id: int,
    upstream_sector_ids: list[int],
    downstream_sector_ids: list[int],
    district: str | None = None,
    limit: int = 100,
    bbox: dict[str, float] | None = None,
    selection: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return individual companies with their relation to the target sector.

    Returns a list of dicts with id, name, lng, lat, relation, industry.
    """
    from app.models.company import Company

    sectors = _sector_map(db)

    # build sector_id → company industry names
    all_sector_ids = set([io_sector_id] + upstream_sector_ids + downstream_sector_ids)
    sector_to_company_industries: dict[int, list[str]] = {}
    for sid in all_sector_ids:
        mappings = db.scalars(
            select(IoIndustryMapping.company_industry).where(IoIndustryMapping.io_sector_id == sid)
        ).all()
        sector_to_company_industries[sid] = list(mappings)

    results: list[dict[str, Any]] = []

    def _query(industries: list[str], relation: str) -> None:
        if not industries:
            return
        stmt = (
            select(Company.id, Company.company_name, Company.lng, Company.lat, Company.industry)
            .where(Company.industry.in_(industries))
            .order_by(Company.id)
        )
        if district:
            stmt = stmt.where(Company.district.ilike(f"%{district}%"))
        if bbox:
            stmt = stmt.where(
                Company.lng >= bbox["west"],
                Company.lng <= bbox["east"],
                Company.lat >= bbox["south"],
                Company.lat <= bbox["north"],
            )
        fetch_limit = limit * 3 if selection else limit
        stmt = stmt.limit(fetch_limit)
        raw_rows = db.execute(stmt).all()
        if selection:
            rows = [r for r in raw_rows if _point_in_selection(r[2], r[3], selection)]
        else:
            rows = raw_rows
        for cid, name, lng, lat, ind in rows[:limit]:
            results.append({
                "id": cid,
                "name": name,
                "lng": round(lng, 6),
                "lat": round(lat, 6),
                "relation": relation,
                "industry": ind or "",
            })

    target_industries = sector_to_company_industries.get(io_sector_id, [])
    up_industries: list[str] = []
    for sid in upstream_sector_ids:
        up_industries.extend(sector_to_company_industries.get(sid, []))
    down_industries: list[str] = []
    for sid in downstream_sector_ids:
        down_industries.extend(sector_to_company_industries.get(sid, []))

    _query(target_industries, "target")
    _query(up_industries, "upstream")
    _query(down_industries, "downstream")

    return results
