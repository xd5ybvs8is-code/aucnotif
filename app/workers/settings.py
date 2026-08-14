from arq.connections import RedisSettings

from app.config import get_settings
from app.workers.tasks import poll_auction, send_notification


async def startup(ctx: dict) -> None:
    import uuid

    from app.infrastructure.container import get_worker_provider
    from app.infrastructure.logging import setup_logging, worker_id_var

    setup_logging()
    worker_id_var.set(uuid.uuid4().hex[:8])
    get_worker_provider()


async def shutdown(ctx: dict) -> None:
    from app.infrastructure.container import close_worker_provider
    from app.infrastructure.redis import close_redis

    await close_worker_provider()
    await close_redis()


class WorkerSettings:
    functions = [poll_auction, send_notification]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 20
    job_timeout = 120
    keep_result = 10
    health_check_interval = 30
