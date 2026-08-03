from __future__ import annotations

from pydantic import BaseModel, Field


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


class FeishuTestRequest(BaseModel):
    open_id: str = Field(min_length=3, max_length=128)
    message: str = Field(min_length=1, max_length=20_000)


class FeishuTestResponse(BaseModel):
    success: bool
