"""Gives every request an id (X-Request-ID), puts it on every log line and logs one line per request."""

import re
import uuid
from time import perf_counter

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import get_logger, request_id_var

HEADER = b"x-request-id"
# A caller-supplied id is reused only when it is short and plain, so it is safe to log and echo back.
_SAFE_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")

log = get_logger(__name__)


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        given = dict(scope["headers"]).get(HEADER, b"").decode("latin-1")
        request_id = given if _SAFE_ID.fullmatch(given) else uuid.uuid4().hex
        token = request_id_var.set(request_id)
        started = perf_counter()
        status = 500  # stays 500 if the app fails before it starts a response

        async def send_with_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message["headers"] = [*message.get("headers", []), (HEADER, request_id.encode())]
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            ms = (perf_counter() - started) * 1000
            log.info("%s %s -> %s in %.0f ms", scope["method"], scope["path"], status, ms)
            request_id_var.reset(token)
