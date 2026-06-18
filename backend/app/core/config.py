from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR / ".env", REPO_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Planning AI Platform"
    app_env: str = "dev"
    database_url: str = "sqlite:///./data/app.db"
    company_database_url: str = "sqlite:///./data/companies.db"
    upload_dir: Path = Path("./data/uploads")
    processed_dir: Path = Path("./data/processed")
    land_use_geojson_path: Path = Path("./data/land_use.geojson")
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = "deepseek-v4-pro"
    llm_vision_model: str = "deepseek-v4-pro"
    deepseek_url: str = "https://api.deepseek.com"
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-v4-pro"
    amap_api_key: str = ""
    dify_base_url: str = ""
    dify_api_key: str = ""
    dify_workflow_id: str = ""
    dify_task_hint: str = "图纸+规则综合分析"
    dify_question_field: str = ""
    dify_shape_field: str = ""
    dify_diagram_id_field: str = ""
    cors_origins: str = "*"

    @model_validator(mode="after")
    def _fill_llm_from_deepseek(self) -> "Settings":
        if not self.llm_api_key and self.deepseek_api_key:
            self.llm_api_key = self.deepseek_api_key
        if not self.llm_base_url and self.deepseek_url:
            self.llm_base_url = self.deepseek_url
        if not self.llm_model and self.deepseek_model:
            self.llm_model = self.deepseek_model
        if not self.llm_vision_model and self.deepseek_model:
            self.llm_vision_model = self.deepseek_model
        return self


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.processed_dir.mkdir(parents=True, exist_ok=True)
    settings.upload_dir.parent.mkdir(parents=True, exist_ok=True)
    settings.processed_dir.parent.mkdir(parents=True, exist_ok=True)
    return settings
