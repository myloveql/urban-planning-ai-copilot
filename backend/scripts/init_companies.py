from app.core.database import CompanySessionLocal, init_company_storage
from app.services.company_service import DATASET_PATH, bootstrap_companies, companies_initialized


def main() -> None:
    init_company_storage()
    with CompanySessionLocal() as db:
        if companies_initialized(db):
            print("companies table already initialized")
            return
        print(f"start importing companies from {DATASET_PATH}", flush=True)
        inserted = bootstrap_companies(db)
        print(f"initialized companies from {DATASET_PATH}")
        print(f"inserted rows: {inserted}")


if __name__ == "__main__":
    main()
