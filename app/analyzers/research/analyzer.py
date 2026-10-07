"""Deterministic analysis of research details explicitly supplied by a candidate."""

from app.analyzers.research.scoring import SCORE_METHOD, score_research_evidence
from app.schemas.research import (
    ResearchAnalysisRequest,
    ResearchAnalysisResponse,
    ResearchEvidence,
    ResearchPublicationEvidence,
)


DOMAIN_TERMS = {
    "artificial intelligence and machine learning": ("machine learning", "deep learning", "neural", "artificial intelligence", "llm", "language model"),
    "data science": ("data science", "data analysis", "dataset", "statistical", "analytics"),
    "computer vision": ("computer vision", "image recognition", "object detection", "visual recognition"),
    "natural language processing": ("natural language", "nlp", "text mining", "sentiment analysis"),
    "security and privacy": ("security", "privacy", "cryptography", "vulnerability"),
    "systems and networking": ("distributed systems", "operating system", "network", "cloud computing"),
    "software engineering": ("software engineering", "software testing", "program analysis", "code quality"),
    "human-computer interaction": ("human-computer interaction", "hci", "usability", "user experience"),
    "robotics": ("robotics", "robot", "autonomous"),
}


def _domain_matches(title: str, abstract: str | None) -> tuple[list[str], list[str]]:
    content = f"{title} {abstract or ''}".casefold()
    domains, keywords = [], []
    for domain, terms in DOMAIN_TERMS.items():
        hits = [term for term in terms if term in content]
        if hits:
            domains.append(domain)
            keywords.extend(hits)
    return domains, keywords


def analyze_research(request: ResearchAnalysisRequest) -> ResearchAnalysisResponse:
    publications = []
    evidence = []
    domains_seen: set[str] = set()
    unavailable = {"external publication verification", "acceptance status", "citation count"}
    for index, item in enumerate(request.research):
        domains, keywords = _domain_matches(item.title, item.abstract)
        domains_seen.update(domains)
        if request.candidate_name and item.authors:
            candidate = " ".join(request.candidate_name.casefold().split())
            listed = any(candidate == " ".join(name.casefold().split()) for name in item.authors)
            authorship = "listed_by_candidate" if listed else "not_listed"
        else:
            authorship = "unavailable"
            unavailable.add("candidate authorship for records without candidate_name or author list")
        publication = ResearchPublicationEvidence(
            title=item.title,
            authors=item.authors,
            venue=item.venue,
            year=item.year,
            url=str(item.url) if item.url else None,
            abstract_provided=bool(item.abstract),
            research_domains=domains,
            domain_keywords=keywords,
            candidate_authorship=authorship,
            stated_role=item.role,
            project_connection=item.project_connection,
            project_connection_source="candidate_supplied" if item.project_connection else "unavailable",
        )
        publications.append(publication)
        present = ["title"]
        present.extend(field for field, value in (
            ("authors", item.authors), ("year", item.year), ("venue", item.venue), ("url", item.url),
            ("abstract", item.abstract), ("role", item.role), ("project_connection", item.project_connection),
        ) if value)
        evidence.append(ResearchEvidence(
            finding="Candidate-supplied publication details recorded; no external verification performed.",
            publication_index=index,
            fields=present,
        ))
    if not request.research:
        unavailable.update(("publication details", "research domains", "candidate authorship", "stated role", "project connection"))
    strengths = []
    if domains_seen:
        strengths.append("Research topics were identifiable from candidate-supplied titles or abstracts.")
    if any(item.stated_role for item in publications):
        strengths.append("A stated candidate role was supplied for at least one publication.")
    return ResearchAnalysisResponse(
        publication_count=len(publications),
        publications=publications,
        research_domains=sorted(domains_seen),
        research_score=score_research_evidence(publications),
        score_method=SCORE_METHOD,
        strengths=strengths,
        evidence=evidence,
        unavailable_fields=sorted(unavailable),
    )
