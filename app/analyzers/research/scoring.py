"""Evidence completeness score; this is not a researcher-quality judgment."""

from app.schemas.research import ResearchPublicationEvidence


SCORE_METHOD = (
    "For each supplied record, count the presence of title, author list, year, venue, URL, abstract, "
    "stated role, and project connection; average completeness percentages across records. The score "
    "measures supplied evidence completeness only, not research quality, venue prestige, authorship "
    "verification, or contribution. Empty input has no score."
)


def score_research_evidence(publications: list[ResearchPublicationEvidence]) -> int | None:
    if not publications:
        return None
    flags = []
    for item in publications:
        flags.append(sum((
            bool(item.title), bool(item.authors), item.year is not None, bool(item.venue), bool(item.url),
            item.abstract_provided, bool(item.stated_role), bool(item.project_connection),
        )) / 8)
    return round(sum(flags) / len(flags) * 100)
