import json
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "China Web API"
    environment: str = "development"
    debug: bool = True
    api_v1_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./china_web.db"
    allowed_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"])
    trusted_hosts: list[str] = Field(default_factory=lambda: ["localhost", "127.0.0.1"])
    docs_enabled: bool = True
    upload_dir: str = "uploads"
    upload_url_prefix: str = "/uploads"
    max_upload_size_mb: int = 50
    media_storage: str = "local"
    cloudinary_url: str = ""
    cloudinary_cloud_name: str = ""
    cloudinary_api_key: str = ""
    cloudinary_api_secret: str = ""
    cloudinary_folder: str = "china-web"
    wp_base_url: str = ""
    wp_username: str = ""
    wp_app_password: str = ""
    wp_auto_sync_enabled: bool = False
    wp_auto_sync_interval_seconds: int = 300
    wp_auto_sync_language_code: str = "en"
    wp_auto_sync_status: str = "publish"
    wp_auto_sync_per_page: int = 50
    wp_auto_sync_max_pages: int = 10
    wp_bidirectional_delete_enabled: bool = False
    wp_default_category_slug: str = "corporate-news"
    wp_category_slug_aliases: str = "uncategorized:corporate-news,chua-phan-loai:corporate-news"
    onlyoffice_document_server_url: str = ""
    onlyoffice_callback_base_url: str = ""
    onlyoffice_jwt_secret: str = ""
    onlyoffice_storage_dir: str = "uploads/post-documents"
    onlyoffice_docx_public_base_url: str = ""
    onlyoffice_auto_convert_on_callback: bool = True
    auth_secret_key: str = "change-this-auth-secret"
    access_token_expire_minutes: int = 480
    initial_admin_username: str = "admin"
    initial_admin_password: str = "admin123456"
    log_level: str = "INFO"

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() in {"prod", "production"}

    @field_validator("allowed_origins", "trusted_hosts", mode="before")
    @classmethod
    def split_csv(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]

        normalized = str(value or "").strip()
        if not normalized:
            return []

        # Support JSON array format in .env, e.g. ["http://localhost:5173","http://127.0.0.1:5173"]
        if normalized.startswith("["):
            try:
                parsed = json.loads(normalized)
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            except json.JSONDecodeError:
                pass

        # Fallback to CSV (legacy format)
        items = []
        for raw in normalized.split(","):
            item = raw.strip().strip("'\"")
            if item.startswith("["):
                item = item[1:].strip()
            if item.endswith("]"):
                item = item[:-1].strip()
            if item:
                items.append(item)
        return items

    @field_validator("debug", "docs_enabled", mode="before")
    @classmethod
    def parse_bool_like(cls, value: bool | str) -> bool:
        if isinstance(value, bool):
            return value
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on", "debug"}:
            return True
        if normalized in {"0", "false", "no", "off", "release", "prod", "production"}:
            return False
        raise ValueError(f"Unsupported boolean value: {value}")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
