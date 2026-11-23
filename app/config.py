"""Runtime settings, read from environment variables (all optional)."""
import os
from dataclasses import dataclass, field
from pathlib import Path


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def _list(name: str, default: str) -> list:
    return [x.strip().lower() for x in os.getenv(name, default).split(",") if x.strip()]


@dataclass(frozen=True)
class Settings:
    refresh_minutes: int = _int("REFRESH_MINUTES", 30)              # job boards
    board_refresh_minutes: int = _int("BOARD_REFRESH_MINUTES", 60)  # company career sites
    board_detail_limit: int = _int("BOARD_DETAIL_LIMIT", 150)       # max new descriptions per company per refresh
    board_countries: list = field(default_factory=lambda: _list("BOARD_COUNTRIES", "in"))  # extra SmartRecruiters country feeds
    live_search_timeout: float = float(os.getenv("LIVE_SEARCH_TIMEOUT", "4"))
    live_cache_minutes: int = _int("LIVE_CACHE_MINUTES", 30)
    arbeitnow_pages: int = _int("ARBEITNOW_PAGES", 8)
    max_upload_mb: int = _int("MAX_UPLOAD_MB", 5)
    rate_limit_per_minute: int = _int("RATE_LIMIT_PER_MINUTE", 30)
    trusted_proxy_hops: int = max(1, _int("TRUSTED_PROXY_HOPS", 1))

    default_country: str = os.getenv("DEFAULT_COUNTRY", "in").lower()        # ISO code for keyed searches
    default_country_name: str = os.getenv("DEFAULT_COUNTRY_NAME", "India")

    jsearch_key: str = os.getenv("JSEARCH_API_KEY", "")                       # RapidAPI key
    jsearch_cache_minutes: int = _int("JSEARCH_CACHE_MINUTES", 360)
    adzuna_app_id: str = os.getenv("ADZUNA_APP_ID", "")
    adzuna_app_key: str = os.getenv("ADZUNA_APP_KEY", "")
    adzuna_country: str = os.getenv("ADZUNA_COUNTRY", "in").lower()
    jooble_key: str = os.getenv("JOOBLE_API_KEY", "")
    jooble_host: str = os.getenv("JOOBLE_HOST", "jooble.org")

    data_dir: Path = Path(os.getenv("DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
    user_agent: str = os.getenv("USER_AGENT", "Mozilla/5.0 (compatible; DreamJob/1.0; job matching)")
    cors_origins: list = field(default_factory=lambda: [o for o in os.getenv("CORS_ORIGINS", "").split(",") if o])


settings = Settings()
