"""Logging setup. Answers and API keys are never logged; only decisions and ids.

Every log line carries the id of the request it belongs to ("-" outside a request).
"""

import logging
from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)s %(name)s [%(request_id)s]: %(message)s",
    )
    for handler in logging.getLogger().handlers:
        if not any(isinstance(f, _RequestIdFilter) for f in handler.filters):
            handler.addFilter(_RequestIdFilter())


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
