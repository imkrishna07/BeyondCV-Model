"""Evidence completeness scoring for certifications, separate from extraction."""

from app.schemas.certifications import CertificationEvidenceItem


SCORE_METHOD = (
    "Average completeness of supplied certification records: name, issuer, date, domain, and URL "
    "each contribute 20 points. The score measures evidence completeness only; it does not rate "
    "certification difficulty, holder ability, or the number of credentials. Empty input scores 0."
)


def score_certifications(certifications: list[CertificationEvidenceItem]) -> int:
    if not certifications:
        return 0
    per_record = []
    for item in certifications:
        supplied = (bool(item.name), bool(item.issuer), item.date is not None, bool(item.domain), bool(item.url))
        per_record.append(sum(supplied) * 20)
    return round(sum(per_record) / len(per_record))
