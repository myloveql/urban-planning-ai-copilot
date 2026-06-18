from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.companies import router as companies_router
from app.api.diagrams import router as diagrams_router
from app.api.land_use import router as land_use_router
from app.api.pois import router as pois_router
from app.api.qa import router as qa_router
from app.core.config import get_settings
from app.core.database import Base, engine, init_company_storage
from app.models.diagram import Diagram  # noqa: F401

settings = get_settings()
Base.metadata.create_all(bind=engine)
init_company_storage()

app = FastAPI(title=settings.app_name)

origins = [origin.strip() for origin in settings.cors_origins.split(",")] if settings.cors_origins != "*" else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(diagrams_router, prefix="/api")
app.include_router(qa_router, prefix="/api")
app.include_router(companies_router, prefix="/api")
app.include_router(pois_router, prefix="/api")
app.include_router(land_use_router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok", "app": settings.app_name}
