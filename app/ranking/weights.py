"""Deterministic job-domain-specific component weight profiles."""

from app.schemas.job import JobRequirementVector


COMPONENTS = (
    "skills", "projects", "github", "coding", "kaggle", "research",
    "certifications", "achievements", "experience", "education",
)

WEIGHT_PROFILES: dict[str, dict[str, float]] = {
    "backend": {
        "skills": 0.22, "projects": 0.23, "github": 0.12, "coding": 0.08,
        "kaggle": 0.03, "research": 0.03, "certifications": 0.05,
        "achievements": 0.05, "experience": 0.14, "education": 0.05,
    },
    "frontend": {
        "skills": 0.27, "projects": 0.22, "github": 0.12, "coding": 0.04,
        "kaggle": 0.03, "research": 0.02, "certifications": 0.04,
        "achievements": 0.04, "experience": 0.14, "education": 0.08,
    },
    "ml_research": {
        "skills": 0.21, "projects": 0.16, "github": 0.08, "coding": 0.05,
        "kaggle": 0.12, "research": 0.20, "certifications": 0.04,
        "achievements": 0.04, "experience": 0.07, "education": 0.03,
    },
    "competitive_programming": {
        "skills": 0.12, "projects": 0.08, "github": 0.05, "coding": 0.46,
        "kaggle": 0.02, "research": 0.04, "certifications": 0.02,
        "achievements": 0.10, "experience": 0.06, "education": 0.05,
    },
    "cloud_devops": {
        "skills": 0.23, "projects": 0.16, "github": 0.12, "coding": 0.04,
        "kaggle": 0.02, "research": 0.02, "certifications": 0.15,
        "achievements": 0.04, "experience": 0.15, "education": 0.07,
    },
    "general_software": {
        "skills": 0.22, "projects": 0.20, "github": 0.12, "coding": 0.08,
        "kaggle": 0.04, "research": 0.05, "certifications": 0.05,
        "achievements": 0.06, "experience": 0.12, "education": 0.06,
    },
}


def select_weight_profile(job: JobRequirementVector) -> tuple[str, dict[str, float]]:
    """Choose a deterministic profile from explicit domain/role signals."""
    text = f"{job.domain or ''} {job.role or ''}".casefold()
    if any(term in text for term in ("competitive programming", "programming contest", "algorithmic competition")):
        key = "competitive_programming"
    elif any(term in text for term in ("machine learning", "ml engineer", "data science", "research scientist", "artificial intelligence")):
        key = "ml_research"
    elif any(term in text for term in ("frontend", "front-end", "user interface")):
        key = "frontend"
    elif any(term in text for term in ("backend", "back-end", "server-side")):
        key = "backend"
    elif any(term in text for term in ("cloud", "devops", "site reliability")):
        key = "cloud_devops"
    else:
        key = "general_software"
    return key, dict(WEIGHT_PROFILES[key])
