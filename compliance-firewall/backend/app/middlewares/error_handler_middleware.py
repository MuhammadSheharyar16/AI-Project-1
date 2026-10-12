"""Global error handling: app errors become clean JSON responses, anything unexpected becomes a logged 500."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.exceptions import AppError
from app.core.logging import get_logger

log = get_logger(__name__)


async def _app_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)


async def _unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    # The details go to the log only: callers never see internal messages.
    log.error("unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse({"detail": "internal server error"}, status_code=500)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error)
    app.add_exception_handler(Exception, _unexpected_error)
