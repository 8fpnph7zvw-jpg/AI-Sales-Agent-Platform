from __future__ import annotations

from app.core.exceptions import ServiceConfigurationError, UpstreamServiceError


class FeishuConfigurationError(ServiceConfigurationError):
    def __init__(self) -> None:
        super().__init__(
            "Feishu is disabled or FEISHU_APP_ID/FEISHU_APP_SECRET are not configured."
        )


class FeishuAPIError(UpstreamServiceError):
    def __init__(
        self,
        message: str,
        *,
        upstream_status_code: int | None = None,
        error_code: str = "FEISHU_API_ERROR",
    ) -> None:
        super().__init__(
            "Feishu",
            message,
            retryable=True,
            upstream_status_code=upstream_status_code,
            error_code=error_code,
        )
