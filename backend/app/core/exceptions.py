from __future__ import annotations

from typing import Any


class AppError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or []


class AuthenticationError(AppError):
    def __init__(self, message: str = "Authentication failed.") -> None:
        super().__init__(401, "AUTHENTICATION_FAILED", message)


class PermissionDeniedError(AppError):
    def __init__(self, message: str = "Permission denied.") -> None:
        super().__init__(403, "PERMISSION_DENIED", message)


class ResourceNotFoundError(AppError):
    def __init__(self, resource: str) -> None:
        super().__init__(404, "RESOURCE_NOT_FOUND", f"{resource} was not found.")


class ConflictError(AppError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(409, code, message)


class ServiceConfigurationError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(503, "SERVICE_NOT_CONFIGURED", message)


class UpstreamServiceError(AppError):
    def __init__(
        self,
        service: str,
        message: str,
        *,
        retryable: bool = False,
        upstream_status_code: int | None = None,
        error_code: str = "UPSTREAM_SERVICE_ERROR",
    ) -> None:
        super().__init__(502, error_code, f"{service}: {message}")
        self.retryable = retryable
        self.upstream_status_code = upstream_status_code
        self.retry_count = 0
