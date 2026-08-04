from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class FeishuTenantTokenResponse(BaseModel):
    code: int
    msg: str = ""
    tenant_access_token: str | None = None
    expire: int = 7200


class FeishuMessageData(BaseModel):
    message_id: str | None = None


class FeishuMessageResponse(BaseModel):
    code: int
    msg: str = ""
    data: FeishuMessageData | None = None


class FeishuSendResult(BaseModel):
    message_id: str | None = None


class FeishuTestResponse(BaseModel):
    success: bool
    message: str = "AI Sales Agent 飞书通知测试成功"
    message_id: str | None = None


class FeishuConfigStatusResponse(BaseModel):
    connector_id: str
    configured_keys: list[str]
    status: str
    health_status: str | None
    last_health_check_at: datetime | None
