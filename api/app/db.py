from functools import lru_cache

from supabase import Client, create_client

from app.config import get_settings


@lru_cache
def get_client() -> Client:
    """Supabase client authenticated with the service-role key.

    Cached because creating the client sets up an HTTP session; on Vercel the
    cache survives for the lifetime of a warm serverless instance.
    """
    settings = get_settings()
    if not settings.supabase_service_role_key:
        raise RuntimeError(
            "SUPABASE_SERVICE_ROLE_KEY is not set. Run `supabase start` and copy "
            "the service_role key into your .env file."
        )
    return create_client(settings.supabase_url, settings.supabase_service_role_key)
