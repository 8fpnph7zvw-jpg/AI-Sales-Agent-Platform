from app.modules.lead_score.service import LeadScoreService


def test_lead_score_levels_are_stable() -> None:
    assert LeadScoreService._level(80) == "hot"
    assert LeadScoreService._level(60) == "warm"
    assert LeadScoreService._level(40) == "nurture"
    assert LeadScoreService._level(39.99) == "cold"
