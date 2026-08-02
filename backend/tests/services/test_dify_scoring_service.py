import pytest

from app.services.dify_scoring_service import DifyScoreOutput, _extract_output, score_level


@pytest.mark.parametrize(
    ("score", "level"),
    [(100, "A"), (90, "A"), (89, "B"), (70, "B"), (69, "C"), (40, "C"), (39, "D"), (0, "D")],
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


def test_rejects_level_that_does_not_match_score() -> None:
    with pytest.raises(ValueError):
        DifyScoreOutput(score=80, level="A", need_follow=True, reason="Mismatch")
