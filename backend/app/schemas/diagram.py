from datetime import datetime
from typing import Any

from pydantic import BaseModel


class DiagramOut(BaseModel):
    id: int
    filename: str
    original_path: str
    processed_path: str | None
    legend_json: dict[str, str]
    scale_json: dict[str, Any]
    image_width: int
    image_height: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DiagramListOut(BaseModel):
    items: list[DiagramOut]


class ScaleCalibrationRequest(BaseModel):
    meters_per_pixel: float | None = None
    reference_distance_meters: float | None = None
    reference_pixel_length: float | None = None
    scale_text: str | None = None


class DiagramRenameRequest(BaseModel):
    filename: str
