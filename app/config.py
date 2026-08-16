from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Core
    database_url: str = "postgresql+asyncpg://auknotif:auknotif@localhost:5432/auknotif"
    redis_url: str = "redis://localhost:6379/0"
    telegram_bot_token: str = ""
    log_level: str = "INFO"
    sentry_dsn: str | None = None
    environment: str = "development"
    default_language: str = "ru"

    # Yahoo provider
    yahoo_request_timeout: float = 15.0
    yahoo_rate_limit: float = 1.0
    yahoo_user_agent: str = "Mozilla/5.0 (compatible; AukNotif/0.1; +https://example.com/bot)"
    yahoo_max_consecutive_errors: int = 5
    yahoo_backoff_base_seconds: float = 30.0
    yahoo_backoff_max_seconds: float = 3600.0
    store_raw_data: bool = False

    # Polling intervals (seconds)
    poll_interval_gt_24h: int = 21600
    poll_interval_6_24h: int = 1800
    poll_interval_1_6h: int = 600
    poll_interval_30_60m: int = 120
    poll_interval_15_30m: int = 60
    poll_interval_lt_15m: int = 60

    # Scheduler / worker
    scheduler_tick_seconds: int = 5
    poll_lock_ttl_seconds: int = 90
    poll_job_max_retries: int = 1
    unwatch_grace_period_seconds: int = 600

    # Notifications
    notify_30m_before_seconds: int = 1800
    notify_15m_before_seconds: int = 900
    notify_5m_before_seconds: int = 300
    telegram_send_max_retries: int = 5
    telegram_send_retry_base_seconds: float = 5.0
    telegram_rate_limit: float = 25.0

    # Observability
    metrics_enabled: bool = True
    snapshot_retention_days: int = 90


@lru_cache
def get_settings() -> Settings:
    return Settings()
