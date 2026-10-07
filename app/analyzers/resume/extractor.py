"""Rule-based resume text extraction with no generated or inferred facts."""

from collections.abc import Iterable
from io import BytesIO
import re
from typing import TypeVar

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.schemas.resume import (
    ResumeAchievement,
    ResumeAnalysisResponse,
    ResumeCertification,
    ResumeEducation,
    ResumeExperience,
    ResumeProject,
    ResumeResearch,
    ResumeSkill,
    ResumeFact,
)


class InvalidResumePDF(ValueError):
    """The upload is not a readable PDF document."""


class EmptyResume(ValueError):
    """The PDF contains no extractable text."""


class ResumeExtractionError(RuntimeError):
    """The PDF parser failed for an unexpected reason."""


SECTION_ALIASES: dict[str, tuple[str, ...]] = {
    "skills": ("skills", "technical skills", "core competencies", "technologies"),
    "education": ("education", "academic background", "academics"),
    "experience": (
        "experience", "work experience", "professional experience", "employment history",
    ),
    "projects": ("projects", "selected projects", "personal projects"),
    "certifications": ("certifications", "certificates", "licenses and certifications"),
    "achievements": (
        "achievements", "awards", "honors", "honours", "competitions",
        "open source contributions", "open-source contributions",
    ),
    "research": (
        "research", "research experience", "research publications", "research and publications",
        "research & publications", "technical research", "security research",
        "security research and publications", "security research & publications",
        "publications", "publication", "technical publications",
    ),
}

_HEADER_LOOKUP = {
    re.sub(r"[^a-z0-9 ]", "", alias.lower()).strip(): section
    for section, aliases in SECTION_ALIASES.items()
    for alias in aliases
}


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract page text from PDF bytes and distinguish invalid/empty documents."""
    if not pdf_bytes.startswith(b"%PDF-"):
        raise InvalidResumePDF("The uploaded file is not a PDF.")

    try:
        reader = PdfReader(BytesIO(pdf_bytes), strict=True)
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except (PdfReadError, OSError, ValueError) as exc:
        raise InvalidResumePDF("The uploaded PDF is invalid or unreadable.") from exc
    except Exception as exc:  # Parser/library failures should become an API error, not a crash.
        raise ResumeExtractionError("The PDF text could not be extracted.") from exc

    if not text.strip():
        raise EmptyResume("No extractable text was found in the PDF.")
    return text


def _normalize_header(line: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", line.lower()).strip()


_RESEARCH_CONTENT_TERMS = re.compile(
    r"\b(research|publication|published|paper|write[- ]?up|study|studied|investigation|"
    r"investigated|security analysis|vulnerability analysis|responsible vulnerability disclosures?|"
    r"responsible disclosure)\b", re.I
)
_ACHIEVEMENT_CONTENT_TERMS = re.compile(
    r"\b(award|winner|finalist|ranked|medal|competition|achievement|contribut(?:e|ed|ion|ions)|"
    r"achievements|open[- ]source|public speaking|speaker|presented|presentation|maintainer|"
    r"cve\s*(?:credit|credits)|credited)\b", re.I
)


def _heading_categories(line: str) -> set[str] | None:
    """Recognize plain or compound section headings without matching prose sentences."""
    candidate = line.strip().rstrip(":").strip()
    if len(candidate.split()) > 14 or re.search(r"[.!?]", candidate):
        return None
    normalized = _normalize_header(candidate)
    exact = _HEADER_LOOKUP.get(normalized)
    if exact:
        return {exact}

    categories: set[str] = set()
    if re.search(r"\b(research|publication|publications)\b", normalized):
        categories.add("research")
    if re.search(
        r"\b(achievement|achievements|award|awards|honor|honors|honour|honours|"
        r"competition|competitions|contribution|contributions)\b|public speaking|open source",
        normalized,
    ):
        categories.add("achievements")
    # A compound title may include a known section alongside research/achievement concepts.
    for section, aliases in SECTION_ALIASES.items():
        if section in {"research", "achievements"}:
            continue
        for alias in aliases:
            alias_normalized = _normalize_header(alias)
            if re.search(rf"\b{re.escape(alias_normalized)}\b", normalized):
                categories.add(section)
                break
    return categories or None


def _route_compound_section_line(line: str, categories: set[str]) -> set[str]:
    """Use line evidence to route content under headings that name multiple categories."""
    if len(categories) == 1:
        return categories
    matched: set[str] = set()
    if "research" in categories and _RESEARCH_CONTENT_TERMS.search(line):
        matched.add("research")
    if "achievements" in categories and _ACHIEVEMENT_CONTENT_TERMS.search(line):
        matched.add("achievements")
    # Do not duplicate ambiguous lines across categories; leave them uncategorized.
    return matched


def _section_lines(text: str) -> dict[str, list[str]]:
    sections = {name: [] for name in SECTION_ALIASES}
    current: set[str] | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        # Headings may be plain aliases or compound category titles. Boundaries
        # and sentence checks prevent ordinary descriptive prose from becoming a heading.
        matched = _heading_categories(line)
        if matched:
            current = matched
            continue

        if current is not None:
            for category in _route_compound_section_line(line, current):
                sections[category].append(line)

    return sections


FactT = TypeVar("FactT", bound=ResumeFact)


def _facts(lines: Iterable[str], schema: type[FactT]) -> list[FactT]:
    return [schema(details=line) for line in lines if line.strip()]


def analyze_resume_text(text: str) -> ResumeAnalysisResponse:
    """Convert recognized section content into typed facts, preserving source text."""
    if not text.strip():
        raise EmptyResume("No extractable text was found in the PDF.")

    sections = _section_lines(text)
    skills: list[ResumeSkill] = []
    for line in sections["skills"]:
        # Skills sections commonly use comma/semicolon separated terms. Keep
        # other line formats intact rather than guessing at their boundaries.
        parts = re.split(r"[,;|]", line)
        skills.extend(ResumeSkill(name=part.strip(" \t-*•")) for part in parts if part.strip(" \t-*•"))

    return ResumeAnalysisResponse(
        skills=skills,
        education=_facts(sections["education"], ResumeEducation),
        experience=_facts(sections["experience"], ResumeExperience),
        projects=_facts(sections["projects"], ResumeProject),
        certifications=_facts(sections["certifications"], ResumeCertification),
        achievements=_facts(sections["achievements"], ResumeAchievement),
        research=_facts(sections["research"], ResumeResearch),
    )
