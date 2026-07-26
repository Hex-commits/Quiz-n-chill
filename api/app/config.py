from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from the environment.

    Locally these come from the repo-root `.env` (see `.env.example`); on Vercel
    they come from the project's environment variables.
    """

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Supabase. The service-role key bypasses row level security, so it must
    # never be exposed to the browser -- only this backend holds it.
    supabase_url: str = "http://127.0.0.1:54321"
    supabase_service_role_key: str = ""

    # Comma-separated list of origins allowed to call this API.
    cors_origins: str = "http://localhost:3000"

    environment: str = "development"

    # Shared secret for the /admin routes. Empty is tolerated in development
    # only; `app.security` refuses to start an unprotected admin surface in any
    # other environment.
    admin_token: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_development(self) -> bool:
        return self.environment == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
