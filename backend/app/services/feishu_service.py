from __future__ import annotations

import json

import httpx

from app.core.config import Settings
from app.core.exceptions import ServiceConfigurationError, UpstreamServiceError


class FeishuService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def configured(self) -> bool:
        return bool(self.settings.feishu_app_id and self.settings.feishu_app_secret)

    async def send_message(self, feishu_open_id: str, content: str) -> None:
        if not self.configured:
            raise ServiceConfigurationError(
                "FEISHU_APP_ID and FEISHU_APP_SECRET are not configured."
            )
        try:
            async with httpx.AsyncClient(
                base_url=self.settings.feishu_api_base_url.rstrip("/") + "/",
                timeout=self.settings.feishu_timeout_seconds,
            ) as client:
                token_response = await client.post(
                    "open-apis/auth/v3/tenant_access_token/internal",
                    json={
                        "app_id": self.settings.feishu_app_id,
                        "app_secret": self.settings.feishu_app_secret,
                    },
                )
                token_response.raise_for_status()
                token_body = token_response.json()
                token = token_body.get("tenant_access_token")
                if token_body.get("code") != 0 or not token:
                    raise ValueError(str(token_body.get("msg") or "token request rejected"))
                response = await client.post(
                    "open-apis/im/v1/messages",
                    params={"receive_id_type": "open_id"},
                    headers={"Authorization": f"Bearer {token}"},
                    json={
                        "receive_id": feishu_open_id,
                        "msg_type": "text",
                        "content": json.dumps({"text": content}, ensure_ascii=False),
                    },
                )
                response.raise_for_status()
                body = response.json()
                if body.get("code") != 0:
                    raise ValueError(str(body.get("msg") or "message request rejected"))
        except (httpx.HTTPError, ValueError) as exc:
            raise UpstreamServiceError(
                "Feishu",
                "could not send the sales notification",
                retryable=True,
                error_code="FEISHU_SEND_FAILED",
            ) from exc
