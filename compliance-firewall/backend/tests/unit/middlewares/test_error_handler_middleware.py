from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.exceptions import NotFoundError, TooManyRequestsError
from app.middlewares.error_handler_middleware import register_error_handlers


def _app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/missing")
    def missing() -> None:
        raise NotFoundError("thing 7 not found")

    @app.get("/busy")
    def busy() -> None:
        raise TooManyRequestsError("too many requests, slow down")

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("secret internal detail")

    return app


def test_app_error_when_raised_returns_its_status_and_detail() -> None:
    response = TestClient(_app()).get("/missing")

    assert response.status_code == 404 and response.json() == {"detail": "thing 7 not found"}


def test_app_error_when_it_has_headers_sends_them() -> None:
    response = TestClient(_app()).get("/busy")

    assert response.status_code == 429 and response.headers["retry-after"] == "60"


def test_unexpected_error_when_raised_returns_500_without_internal_details() -> None:
    response = TestClient(_app(), raise_server_exceptions=False).get("/boom")

    assert response.status_code == 500 and response.json() == {"detail": "internal server error"}
    assert "secret" not in response.text
