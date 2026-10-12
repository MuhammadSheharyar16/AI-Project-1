import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.logging import get_logger, request_id_var
from app.middlewares.request_id_middleware import RequestIdMiddleware


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)

    @app.get("/ping")
    def ping() -> dict[str, str]:
        get_logger("test").info("inside the request")
        return {"request_id": request_id_var.get()}

    return app


def test_request_when_no_id_given_generates_one_and_returns_it() -> None:
    response = TestClient(_app()).get("/ping")

    request_id = response.headers["x-request-id"]
    assert len(request_id) == 32 and response.json() == {"request_id": request_id}


def test_request_when_safe_id_given_reuses_it() -> None:
    response = TestClient(_app()).get("/ping", headers={"X-Request-ID": "abc-123"})

    assert response.headers["x-request-id"] == "abc-123"


def test_request_when_unsafe_id_given_replaces_it() -> None:
    response = TestClient(_app()).get("/ping", headers={"X-Request-ID": "bad id\n<script>"})

    assert response.headers["x-request-id"] != "bad id\n<script>"
    assert len(response.headers["x-request-id"]) == 32


def test_request_when_finished_logs_one_line_and_resets_id(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        TestClient(_app()).get("/ping", headers={"X-Request-ID": "abc-123"})

    assert any("GET /ping -> 200" in r.getMessage() for r in caplog.records)
    assert request_id_var.get() == "-"
