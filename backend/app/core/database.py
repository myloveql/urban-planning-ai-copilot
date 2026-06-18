from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import get_settings

settings = get_settings()
engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
company_engine = create_engine(settings.company_database_url, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
CompanySessionLocal = sessionmaker(bind=company_engine, autoflush=False, autocommit=False)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_company_db():
    db = CompanySessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_company_storage():
    from app.models.company import Company
    from app.models.poi import Poi

    inspector = inspect(company_engine)
    if not inspector.has_table(Company.__tablename__):
        Company.__table__.create(bind=company_engine)
    if not inspector.has_table(Poi.__tablename__):
        Poi.__table__.create(bind=company_engine)
