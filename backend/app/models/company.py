from sqlalchemy import Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Company(Base):
    __tablename__ = "companies"
    __table_args__ = (
        Index("ix_companies_lng_lat", "lng", "lat"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    legal_representative: Mapped[str | None] = mapped_column(String(128), nullable=True)
    registered_capital: Mapped[str | None] = mapped_column(String(128), nullable=True)
    paid_in_capital: Mapped[str | None] = mapped_column(String(128), nullable=True)
    established_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
    district: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    industry: Mapped[str | None] = mapped_column(String(128), nullable=True)
    company_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    insured_count: Mapped[str | None] = mapped_column(String(64), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    business_scope: Mapped[str | None] = mapped_column(Text, nullable=True)
    lng: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    lat: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    survival_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
