from __future__ import annotations

import logging

import httpx
import pytest

from app.core.config import Settings
from app.core.exceptions import UpstreamServiceError
from app.services.dify_scoring_service import (
    DifyScoreOutput,
    DifyScoringInput,
    DifyScoringService,
    _extract_output,
    score_level,
)


class FakeAsyncClient:
    response: httpx.Response

    def __init__(self, **_kwargs: object) -> None:
        pass

    async def __aenter__(self) -> FakeAsyncClient:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def post(self, *_args: object, **_kwargs: object) -> httpx.Response:
        return self.response


def scoring_input() -> DifyScoringInput:
    return DifyScoringInput(
        chat_history="customer: Need 1000 units",
        customer_profile="{}",
        product_requirement="Jacket",
        quantity="1000",
        country="US",
        user="customer-public-id",
    )


@pytest.mark.parametrize(
    ("score", "level"),
    [(100, "A"), (70, "A"), (69, "B"), (31, "B"), (30, "C"), (0, "C")],
)
def test_score_levels_match_business_rules(score: int, level: str) -> None:
    assert score_level(score) == level
    output = DifyScoreOutput(
        score=score,
        level=level,
        need_follow=score >= 80,
        reason="Customer intent was evaluated.",
    )
    assert output.score == score


def test_extracts_json_string_from_dify_workflow_outputs() -> None:
    body = {
        "data": {
            "outputs": {
                "result": '{"score":90,"level":"A","need_follow":true,"reason":"Ready"}'
            }
        }
    }
    assert _extract_output(body)["score"] == 90


def test_accepts_chinese_need_follow_label_from_workflow() -> None:
    output = DifyScoreOutput.model_validate(
        {
            "score": 95,
            "level": "A",
            "need_follow": "是",
            "reason": "客户明确要求报价",
        }
    )
    assert output.need_follow is True


def test_backend_overrides_workflow_level_from_score() -> None:
    output = DifyScoreOutput(
        score=85,
        level="invalid-workflow-level",
        need_follow="yes",  # type: ignore[arg-type]
        reason="High intent",
    )

    assert output.level == "A"
    assert output.need_follow is True


def test_extracts_structured_output_object() -> None:
    body = {
        "data": {
            "outputs": {
                "structured_output": {
                    "score": 85,
                    "level": "ignored",
                    "need_follow": "yes",
                    "reason": "Ready",
                }
            }
        }
    }

    assert _extract_output(body)["score"] == 85


def test_extracts_structured_output_json_string() -> None:
    body = {
        "data": {
            "outputs": {
                "structured_output": (
                    '{"score":85,"level":"ignored",'
                    '"need_follow":"yes","reason":"Ready"}'
                )
            }
        }
    }

    assert _extract_output(body)["need_follow"] == "yes"


def test_extracts_score_result_object() -> None:
    body = {
        "data": {
            "outputs": {
                "score_result": {
                    "score": 55,
                    "need_follow": False,
                    "reason": "Nurture",
                }
            }
        }
    }

    assert _extract_output(body)["score"] == 55


@pytest.mark.asyncio
async def test_http_error_logs_status_content_type_and_summary(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    FakeAsyncClient.response = httpx.Response(
        400,
        json={"code": "invalid_param", "message": "Input variable is missing"},
        headers={"content-type": "application/json"},
        request=httpx.Request("POST", "https://api.dify.ai/v1/workflows/run"),
    )
    monkeypatch.setattr(
        "app.services.dify_scoring_service.httpx.AsyncClient",
        FakeAsyncClient,
    )
    caplog.set_level(logging.WARNING)
    service = DifyScoringService(
        Settings(_env_file=None, dify_scoring_api_key="workflow-key")
    )

    with pytest.raises(UpstreamServiceError) as exc_info:
        await service.run(scoring_input())

    assert exc_info.value.code == "DIFY_SCORING_HTTP_400"
    assert "status_code=400" in caplog.text
    assert "content_type=application/json" in caplog.text
    assert "invalid_param" in caplog.text


@pytest.mark.asyncio
async def test_invalid_json_logs_response_summary(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    FakeAsyncClient.response = httpx.Response(
        200,
        text="<html>gateway response</html>",
        headers={"content-type": "text/html"},
        request=httpx.Request("POST", "https://api.dify.ai/v1/workflows/run"),
    )
    monkeypatch.setattr(
        "app.services.dify_scoring_service.httpx.AsyncClient",
        FakeAsyncClient,
    )
    caplog.set_level(logging.WARNING)
    service = DifyScoringService(
        Settings(_env_file=None, dify_scoring_api_key="workflow-key")
    )

    with pytest.raises(UpstreamServiceError) as exc_info:
        await service.run(scoring_input())

    assert exc_info.value.code == "DIFY_SCORING_INVALID_JSON"
    assert "status_code=200" in caplog.text
    assert "content_type=text/html" in caplog.text
    assert "gateway response" in caplog.text
