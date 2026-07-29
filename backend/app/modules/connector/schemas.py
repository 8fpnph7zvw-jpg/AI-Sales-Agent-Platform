from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ConnectorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    public_id: str = Field(serialization_alias="id")
    provider: str
    name: str
    status: str
    session_id: str | None
    phone: str | None
    last_connected_at: datetime | None
    last_disconnect_reason: str | None
    capabilities: list[str]
    external_account_id: str
    health_status: str | None
    last_health_check_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ConnectorListResponse(BaseModel):
    data: list[ConnectorRead]


class ConnectorConfigValue(BaseModel):
    key: str = Field(min_length=1, max_length=120, pattern=r"^[a-zA-Z0-9_.-]+$")
    value: Any
    value_type: str = Field(default="string", max_length=24)
    is_secret: bool = True


class ConnectorConfigRequest(BaseModel):
    connector_id: str = Field(min_length=26, max_length=26)
    values: list[ConnectorConfigValue] = Field(min_length=1, max_length=100)


class ConnectorConfigResponse(BaseModel):
    connector_id: str
    configured_keys: list[str]
    key_version: str
