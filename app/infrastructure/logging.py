import logging
import sys
import uuid
from contextvars import ContextVar

import structlog

from app.config import get_settings

correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="-")
worker_id_var: ContextVar[str] = ContextVar("worker_id", default="-")


def _add_context(logger, method_name, event_dict):
    event_dict["correlation_id"] = correlation_id_var.get()
    event_dict["worker_id"] = worker_id_var.get()
    return event_dict


def setup_logging() -> None:
    level = getattr(logging, get_settings().log_level.upper(), logging.INFO)
    logging.basicConfig(stream=sys.stdout, level=level, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _add_context,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def new_correlation_id() -> str:
    value = uuid.uuid4().hex[:12]
    correlation_id_var.set(value)
    return value
