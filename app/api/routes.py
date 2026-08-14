import logging

from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from app.config import get_settings
from app.db import get_session_factory
from app.infrastructure.redis import get_redis

logger = logging.getLogger("auknotif.api")


def create_app() -> FastAPI:
    app = FastAPI(title="AukNotif", version="0.1.0")

    @app.get("/health")
    async def health() -> dict:
        checks: dict[str, str] = {}

        try:
            session_factory = get_session_factory()
            async with session_factory() as session:
                await session.execute(text("SELECT 1"))
            checks["postgres"] = "ok"
        except Exception as exc:
            logger.error("health_check_postgres_failed", exc_info=exc)
            checks["postgres"] = f"error: {type(exc).__name__}"

        try:
            await get_redis().ping()
            checks["redis"] = "ok"
        except Exception as exc:
            logger.error("health_check_redis_failed", exc_info=exc)
            checks["redis"] = f"error: {type(exc).__name__}"

        return {"status": "ok" if all(v == "ok" for v in checks.values()) else "degraded", **checks}

    @app.get("/ready")
    async def ready() -> dict:
        return {"status": "ready"}

    @app.get("/metrics")
    async def metrics() -> Response:
        if not get_settings().metrics_enabled:
            return Response(status_code=404)
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app


app = create_app()
