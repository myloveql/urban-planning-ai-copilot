from pydantic import BaseModel


class PoiPointOut(BaseModel):
    id: int
    name: str
    district: str | None
    major_category: str | None
    middle_category: str | None
    minor_category: str | None
    lng: float
    lat: float


class PoiListOut(BaseModel):
    items: list[PoiPointOut]
    total: int
    truncated: bool


class PoiCategoryOut(BaseModel):
    name: str
    count: int


class PoiCategoryListOut(BaseModel):
    items: list[PoiCategoryOut]
