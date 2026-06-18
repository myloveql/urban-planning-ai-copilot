from sqlalchemy import Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Poi(Base):
    __tablename__ = "pois"
    __table_args__ = (
        Index("ix_pois_lng_lat", "lng", "lat"),
        Index("ix_pois_major_category", "major_category"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    object_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    source_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    district: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    major_category: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    middle_category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    minor_category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lng: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    lat: Mapped[float] = mapped_column(Float, nullable=False, index=True)
