from __future__ import annotations

from typing import Any

import pytest

from app.integrations.feishu.schemas import FeishuSendResult
from app.modules.notification.service import NotificationService


class FakeFeishuService:
    def __init__(self, *, configured: bool) -> None:
        self.configured = configured
        self.calls: list[dict[str, Any]] = []

    async def send_text_message(
        self,
        receiver_open_id: str,
        content: str,
        **context: Any,
    ) -> FeishuSendResult:
        self.calls.append(
            {
                "receiver_open_id": receiver_open_id,
                "content": content,
                **context,
            }
        )
        return FeishuSendResult(message_id="om_test")


@pytest.mark.asyncio
async def test_notify_sales_routes_to_enabled_feishu() -> None:
    feishu = FakeFeishuService(configured=True)
    service = NotificationService(None, None, feishu)  # type: ignore[arg-type]

    sent = await service.notify_sales(
        "ou_receiver",
        "high intent lead",
        customer_id="customer-1",
        user_id="user-1",
    )

    assert sent is True
    assert feishu.calls == [
        {
            "receiver_open_id": "ou_receiver",
            "content": "high intent lead",
            "customer_id": "customer-1",
            "user_id": "user-1",
        }
    ]


@pytest.mark.asyncio
async def test_notify_sales_is_disabled_without_enabled_channel() -> None:
    feishu = FakeFeishuService(configured=False)
    service = NotificationService(None, None, feishu)  # type: ignore[arg-type]

    sent = await service.notify_sales("ou_receiver", "high intent lead")

    assert sent is False
    assert feishu.calls == []
