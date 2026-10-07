"""Transparent component scoring for reported achievement evidence."""

from app.schemas.achievements import AchievementEvidenceItem


SCORE_METHOD = (
    "Average per-record evidence score. Recognition base: winner/award 80, finalist 55, "
    "ranked result 50, participation 15, unspecified outcome 0. Supplied year and domain "
    "each add 5 points. Participant count and achievement count do not increase the score. "
    "Names and participant counts alone do not establish merit. Empty input scores 0."
)

_BASE_POINTS = {
    "winner_award": 80,
    "finalist": 55,
    "ranked": 50,
    "participation": 15,
    "unspecified": 0,
}


def score_achievements(achievements: list[AchievementEvidenceItem]) -> int:
    if not achievements:
        return 0
    points = []
    for item in achievements:
        completeness_bonus = 5 * sum((item.year is not None, bool(item.domain)))
        points.append(min(100, _BASE_POINTS[item.recognition_level] + completeness_bonus))
    return round(sum(points) / len(points))
