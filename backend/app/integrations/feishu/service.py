from __future__ import annotations

import logging
from functools import lru_cache

from app.core.config import get_settings
from app.integrations.feishu.client import FeishuClient
from app.integrations.feishu.schemas import FeishuSendResult

logger = logging.getLogger(__name__)


class FeishuService:
    def __init__(self, client: FeishuClient) -> None:
        self.client = client

    @property
    def configured(self) -> bool:
        return self.client.configured

    async def send_text_message(
        self,
        receiver_open_id: str,
        content: str,
        *,
        customer_id: str | None = None,
        user_id: str | None = None,
    ) -> FeishuSendResult:
        logger.info(
            "feishu_message_send_started customer_id=%s user_id=%s receiver_open_id=%s",
            customer_id,
            user_id,
            receiver_open_id,
        )
        try:
            result = await self.client.send_text_message(receiver_open_id, content)
        except Exception:
            logger.exception(
                "feishu_message_send_failed customer_id=%s user_id=%s receiver_open_id=%s",
                customer_id,
                user_id,
                receiver_open_id,
            )
            raise
        logger.info(
            "feishu_message_send_success customer_id=%s user_id=%s receiver_open_id=%s",
            customer_id,
            user_id,
            receiver_open_id,
        )
        return result

    async def send_message(self, feishu_open_id: str, content: str) -> None:
        """Compatibility alias for the pre-integration service API."""
        await self.send_text_message(feishu_open_id, content)


@lru_cache
def get_feishu_service() -> FeishuService:
    """Return the process-wide service so its client can reuse cached tokens."""
    return FeishuService(FeishuClient(get_settings()))
