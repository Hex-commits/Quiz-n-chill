from functools import lru_cache

from pydantic import Field
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

    supabase_url: str = "http://127.0.0.1:54321"
    supabase_service_role_key: str = ""

    cors_origins: str = (
        "http://localhost:3000,"
        "http://127.0.0.1:3000,"
        "https://quiz-n-chill-web.vercel.app"
    )

    cors_origin_regex: str = r"^https://quiz-n-chill[a-z0-9-]*-hex15hex\.vercel\.app$"

    environment: str = "development"

    first_turn_bonus_seconds: int = Field(default=10, ge=0)

    shared_lobbies: bool = False

    realtime_broadcast: bool = False

    @property
    def lobbies_are_shared(self) -> bool:
        return self.shared_lobbies

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
