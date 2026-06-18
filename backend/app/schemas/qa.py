from typing import Any, Literal

from pydantic import BaseModel, Field


class Point(BaseModel):
    x: float
    y: float


class RegionShape(BaseModel):
    type: Literal["polygon", "circle"]
    points: list[Point] | None = None
    center: Point | None = None
    radius: float | None = None


class MapBbox(BaseModel):
    west: float
    south: float
    east: float
    north: float


class AskRequest(BaseModel):
    diagram_id: int
    question: str = Field(min_length=1)
    shape: RegionShape | None = None
    task_hint: str | None = None
    conversation_id: str | None = None
    image_data_url: str | None = None
    image_name: str | None = None
    map_bbox: MapBbox | None = None
    map_selection: RegionShape | None = None


class AskResponse(BaseModel):
    answer: str
    intent: dict[str, Any]
    tool_results: dict[str, Any]
    conversation_id: str | None = None
