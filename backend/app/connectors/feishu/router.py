from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies.auth import Principal, require_any_permission
from app.integrations.feishu.schemas import FeishuTestRequest, FeishuTestResponse
from app.integrations.feishu.service import FeishuService, get_feishu_service

router = APIRouter(prefix="/connectors/feishu", tags=["Feishu Connector"])


@router.post("/test", response_model=FeishuTestResponse)
async def test_feishu_connector(
    payload: FeishuTestRequest,
    service: Annotated[FeishuService, Depends(get_feishu_service)],
    _principal: Annotated[
        Principal,
        Depends(require_any_permission("connector.manage", "connector.secret_manage")),
    ],
) -> FeishuTestResponse:
    await service.send_text_message(payload.open_id, payload.message)
    return FeishuTestResponse(success=True)
