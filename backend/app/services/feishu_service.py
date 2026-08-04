from __future__ import annotations

import logging

from app.integrations.feishu.client import FeishuClient
from app.integrations.feishu.schemas import FeishuSendResult

logger = logging.getLogger(__name__)


class FeishuService:
    """Enterprise Feishu app operations for one tenant Connector configuration."""

    def __init__(self, client: FeishuClient) -> None:
        self.client = client

    @property
    def configured(self) -> bool:
        return self.client.configured

    async def get_tenant_access_token(self) -> str:
        return await self.client.get_tenant_access_token()

    async def send_message(
        self,
        receive_id: str,
        content: str,
        *,
        customer_id: str | None = None,
        user_id: str | None = None,
    ) -> FeishuSendResult:
        logger.info(
            "feishu_message_send_started customer_id=%s user_id=%s receiver_open_id=%s",
            customer_id,
            user_id,
            receive_id,
        )
        try:
            result = await self.client.send_text_message(receive_id, content)
        except Exception:
            logger.exception(
                "feishu_message_send_failed customer_id=%s user_id=%s receiver_open_id=%s",
                customer_id,
                user_id,
                receive_id,
            )
            raise
        logger.info(
            "feishu_message_send_success customer_id=%s user_id=%s receiver_open_id=%s",
            customer_id,
            user_id,
            receive_id,
        )
        return result

    async def test_connection(self) -> bool:
        await self.get_tenant_access_token()
        return True

    async def send_text_message(
        self,
        receive_id: str,
        content: str,
        **context: str | None,
    ) -> FeishuSendResult:
        """Compatibility alias for existing notification callers."""
        return await self.send_message(receive_id, content, **context)
