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
    #
    # The deployed frontend is listed here rather than left to an environment
    # variable, because it is a fact about this project and not a secret. A
    # CORS failure is also invisible from the server side -- the API answers
    # normally and the browser discards the response -- so the default that
    # needs no setup is the one that should be right.
    #
    # Overridden by CORS_ORIGINS whenever the frontend moves.
    cors_origins: str = (
        "http://localhost:3000,"
        "http://127.0.0.1:3000,"
        "https://quiz-n-chill-web.vercel.app"
    )

    # Origins allowed by pattern rather than by name, for hosts whose URL is not
    # known in advance. Vercel gives every preview deployment its own domain, so
    # without this only production would be able to call the API and every
    # preview would fail CORS.
    #
    # Preview deployments, which get a fresh hostname every time and so can
    # never be named in the list above.
    #
    # Vercel builds them as `<project>-<hash>-<scope>.vercel.app`, e.g.
    #     quiz-n-chill-a7th8ajbs-hex15hex.vercel.app
    # Anchored at both ends on purpose: the project prefix and the account slug
    # together. Matching only the slug would accept any project someone happened
    # to name `something-hex15hex`, whose production alias is claimable by
    # anyone; matching only the prefix would accept another account's fork.
    #
    # Never a bare `.*\.vercel\.app` -- credentials are allowed, so that would
    # let any Vercel project at all call this API as the player.
    #
    # Overridden by CORS_ORIGIN_REGEX; set it empty to allow no previews.
    cors_origin_regex: str = r"^https://quiz-n-chill[a-z0-9-]*-hex15hex\.vercel\.app$"

    environment: str = "development"

    # Where lobbies live. False means "in this process", which is right for one
    # container and wrong for anything that scales horizontally -- serverless
    # included, where every request may land on a fresh instance holding an
    # empty dict. True keeps them in `public.lobbies` instead, so every instance
    # sees the same game.
    #
    # Not history either way: rows carry an expiry and are swept. What is stored
    # is a game in progress, and it goes when the game does.
    shared_lobbies: bool = False

    # Push a one-line "something changed" to Supabase Realtime after every
    # lobby mutation, so clients can stop polling. Off by default: the test
    # suite must not make network calls, and a single-container run works
    # perfectly well on the slow poll alone.
    realtime_broadcast: bool = False

    @property
    def lobbies_are_shared(self) -> bool:
        return self.shared_lobbies

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
