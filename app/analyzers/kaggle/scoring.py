"""Transparent scoring of the completeness and breadth of returned Kaggle evidence."""

from app.schemas.kaggle import KaggleArtifact


SCORE_METHOD = (
    "Evidence score (0-100), not a skill or hiring score: average metadata completeness "
    "across returned notebooks and datasets (title, description, URL, topics, update date), "
    "plus 10 points when both artifact types are present. Artifact counts, medals, and popularity "
    "are not treated as proof of ability. Null means there is insufficient accessible evidence."
)


def score_kaggle_evidence(notebooks: list[KaggleArtifact], datasets: list[KaggleArtifact]) -> int | None:
    artifacts = notebooks + datasets
    if not artifacts:
        return None
    completeness = [
        sum(bool(value) for value in (item.title, item.description, item.url, item.topics, item.last_updated)) / 5
        for item in artifacts
    ]
    type_bonus = 10 if notebooks and datasets else 0
    return min(100, round(sum(completeness) / len(completeness) * 90 + type_bonus))
