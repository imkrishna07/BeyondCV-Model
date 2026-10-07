"""Normalize supplied certification details and assess optional job-text relevance."""

import re

from app.analyzers.certifications.scoring import SCORE_METHOD, score_certifications
from app.schemas.certifications import (
    CertificationAnalysisRequest,
    CertificationAnalysisResponse,
    CertificationEvidence,
    CertificationEvidenceItem,
)


def _tokens(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9+#.]{2,}", text.casefold()) if word not in {"and", "the", "for", "with", "from"}}


def analyze_certifications(request: CertificationAnalysisRequest) -> CertificationAnalysisResponse:
    results = []
    evidence = []
    job_terms = _tokens(request.job_description) if request.job_description else set()
    for index, entry in enumerate(request.certifications):
        name = entry.name.strip()
        issuer = entry.issuer.strip() if entry.issuer and entry.issuer.strip() else None
        domain = entry.domain.strip() if entry.domain and entry.domain.strip() else None
        cert_terms = _tokens(f"{name} {domain or ''}")
        matches = sorted(cert_terms & job_terms)
        relevance = "not_assessed" if not request.job_description else ("relevant" if matches else "not_relevant")
        item = CertificationEvidenceItem(
            name=name,
            issuer=issuer,
            date=entry.date,
            domain=domain,
            url=str(entry.url) if entry.url else None,
            relevance=relevance,
            matched_terms=matches,
        )
        results.append(item)
        fields = ["name"]
        fields.extend(field for field, value in (
            ("issuer", issuer), ("date", entry.date), ("domain", domain), ("url", entry.url),
        ) if value)
        evidence.append(CertificationEvidence(
            finding="Certification details supplied by the candidate; no credential verification was performed.",
            certification_index=index,
            fields=fields,
        ))
    if not results:
        evidence.append(CertificationEvidence(finding="No certification records were supplied."))
    relevant = [item for item in results if item.relevance == "relevant"]
    strengths = []
    if relevant:
        strengths.append(f"{len(relevant)} supplied certification record(s) matched terms in the provided job description.")
    if any(item.url for item in results):
        strengths.append("At least one certification record includes a URL that can be reviewed separately.")
    return CertificationAnalysisResponse(
        certifications=results,
        certification_score=score_certifications(results),
        relevant_certifications=relevant,
        strengths=strengths,
        evidence=evidence,
        score_method=SCORE_METHOD,
        status="available" if results else "no_data",
    )
