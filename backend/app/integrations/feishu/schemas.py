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
    message: str = "AI Sales Agent 测试通知发送成功"
    message_id: str | None = None


class FeishuConfigStatusResponse(BaseModel):
    connector_id: str
    configured_keys: list[str]
    status: str
    health_status: str | None
    last_health_check_at: datetime | None


class FeishuOAuthURLResponse(BaseModel):
    url: str
    expires_in: int


class FeishuOAuthTokenResponse(BaseModel):
    code: int = 0
    access_token: str | None = None
    expires_in: int | None = None
    error: str | None = None
    error_description: str | None = None


class FeishuOAuthUserInfo(BaseModel):
    open_id: str
    name: str | None = None
    mobile: str | None = None
    email: str | None = None
    tenant_key: str | None = None


class FeishuOAuthUserInfoResponse(BaseModel):
    code: int
    msg: str = ""
    data: FeishuOAuthUserInfo | None = None
