import uvicorn

from app.api.routes import app
from app.config import get_settings
from app.infrastructure.logging import setup_logging

if __name__ == "__main__":
    setup_logging()
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level=get_settings().log_level.lower(),
        access_log=False,
    )
