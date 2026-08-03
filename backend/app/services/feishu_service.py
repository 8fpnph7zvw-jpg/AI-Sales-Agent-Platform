from app.core.config import Settings
from app.integrations.feishu.client import FeishuClient
from app.integrations.feishu.service import FeishuService as IntegrationFeishuService
from app.modules.notification.service import NotificationService


class FeishuService(NotificationService):
    """Compatibility facade routing legacy callers through NotificationService."""

    def __init__(self, settings: Settings) -> None:
        super().__init__(None, None, IntegrationFeishuService(FeishuClient(settings)))

    @property
    def configured(self) -> bool:
        return bool(self.feishu and self.feishu.configured)

    async def send_message(self, feishu_open_id: str, content: str) -> None:
        await self.notify_sales(feishu_open_id, content)
