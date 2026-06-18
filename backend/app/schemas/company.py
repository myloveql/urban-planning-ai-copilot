from pydantic import BaseModel


class CompanyPointOut(BaseModel):
    id: int
    company_name: str
    district: str | None
    industry: str | None
    lng: float
    lat: float
    survival_status: str | None


class CompanyDetailOut(BaseModel):
    id: int
    company_name: str
    status: str | None
    legal_representative: str | None
    registered_capital: str | None
    paid_in_capital: str | None
    established_at: str | None
    district: str | None
    industry: str | None
    company_type: str | None
    insured_count: str | None
    address: str | None
    business_scope: str | None
    lng: float
    lat: float
    survival_status: str | None


class CompanyListOut(BaseModel):
    items: list[CompanyPointOut]
    total: int
    truncated: bool
