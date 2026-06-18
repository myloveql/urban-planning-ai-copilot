from app.core.database import CompanySessionLocal, init_company_storage
from app.services.poi_service import DATASET_PATH, bootstrap_pois, pois_initialized


def main() -> None:
    init_company_storage()
    with CompanySessionLocal() as db:
        if pois_initialized(db):
            print("pois table already initialized")
            return
        print(f"start importing pois from {DATASET_PATH}", flush=True)
        inserted = bootstrap_pois(db)
        print(f"initialized pois from {DATASET_PATH}")
        print(f"inserted rows: {inserted}")


if __name__ == "__main__":
    main()
