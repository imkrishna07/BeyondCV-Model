"""Small, explicit normalization helpers used by the candidate feature aggregator."""

import re
from math import log1p
from collections.abc import Iterable


_CANONICAL_SKILLS = {
    "python": "Python",
    "py": "Python",
    "javascript": "JavaScript",
    "js": "JavaScript",
    "typescript": "TypeScript",
    "ts": "TypeScript",
    "c++": "C++",
    "cpp": "C++",
    "c#": "C#",
    "csharp": "C#",
    "golang": "Go",
    "go": "Go",
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "node.js": "Node.js",
    "nodejs": "Node.js",
    "react.js": "React",
    "reactjs": "React",
    "react": "React",
    "next.js": "Next.js",
    "nextjs": "Next.js",
    "fastapi": "FastAPI",
    "django": "Django",
    "vue.js": "Vue.js",
    "vue": "Vue.js",
    "numpy": "NumPy",
    "pandas": "Pandas",
    "scikit-learn": "scikit-learn",
    "sklearn": "scikit-learn",
    "aws": "AWS",
    "gcp": "Google Cloud",
    "google cloud": "Google Cloud",
    "azure": "Azure",
    "docker": "Docker",
    "kubernetes": "Kubernetes",
    "k8s": "Kubernetes",
    "sql": "SQL",
    "html": "HTML",
    "css": "CSS",
    "ml": "Machine Learning",
    "machine learning": "Machine Learning",
    "ai": "Artificial Intelligence",
    "artificial intelligence": "Artificial Intelligence",
}


def normalize_skill_name(name: str) -> str:
    """Normalize casing and common aliases without adding skills not in the input."""
    cleaned = " ".join(name.strip().split())
    if not cleaned:
        return ""
    return _CANONICAL_SKILLS.get(cleaned.casefold(), cleaned)


def deduplicate_skills(skills: Iterable[str]) -> list[str]:
    """Deduplicate canonical names case-insensitively, retaining first-seen order."""
    result: list[str] = []
    seen: set[str] = set()
    for raw in skills:
        canonical = normalize_skill_name(raw)
        key = canonical.casefold()
        if canonical and key not in seen:
            seen.add(key)
            result.append(canonical)
    return result


def normalize_score(value: int | float | None) -> float | None:
    """Convert a source score already defined on 0-100 to 0-1; preserve missingness."""
    if value is None:
        return None
    return round(min(100.0, max(0.0, float(value))) / 100.0, 4)


def normalize_rating(value: int | float | None, reference_ceiling: float) -> float | None:
    """Scale a platform-specific rating to 0-1 using that platform's stated ceiling."""
    if value is None:
        return None
    return round(min(1.0, max(0.0, float(value) / reference_ceiling)), 4)


def normalize_count(value: int | None, reference_ceiling: int) -> float | None:
    """Log-scale a nonnegative count with a metric-specific ceiling, not cross-metric rank."""
    if value is None:
        return None
    bounded = min(max(0, value), reference_ceiling)
    return round(log1p(bounded) / log1p(reference_ceiling), 4)


def canonical_domain(value: str | None) -> str | None:
    """Collapse spacing and casing for grouping explicitly supplied domain labels."""
    if value is None:
        return None
    cleaned = re.sub(r"\s+", " ", value).strip()
    if not cleaned:
        return None
    return cleaned.title()
