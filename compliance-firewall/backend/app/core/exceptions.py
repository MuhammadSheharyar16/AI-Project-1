"""Application errors. The error handler middleware turns each one into an HTTP response.

Services and repositories raise these; routers never build HTTP errors themselves.
"""


class AppError(Exception):
    """Base for every expected error. `detail` is safe to show to the API caller."""

    status_code = 500
    headers: dict[str, str] | None = None

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class UnauthorizedError(AppError):
    """A token is required and was missing or wrong."""

    status_code = 401


class ForbiddenError(AppError):
    """The endpoint or option is switched off by configuration."""

    status_code = 403


class NotFoundError(AppError):
    status_code = 404


class ConflictError(AppError):
    status_code = 409


class TooManyRequestsError(AppError):
    status_code = 429
    headers = {"Retry-After": "60"}


class ServiceUnavailableError(AppError):
    status_code = 503


class VersionConflictError(ConflictError):
    """Another save created the same rules version number first. Retrying is safe."""

    def __init__(self, version: int) -> None:
        super().__init__(f"version {version} already exists; please retry")
