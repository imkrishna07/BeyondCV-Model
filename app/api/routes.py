"""Route registration for the service API."""

from fastapi import APIRouter
from fastapi import File, HTTPException, UploadFile

from app.analyzers.project.analyzer import analyze_project_zip
from app.analyzers.project.file_scanner import (
    MAX_ARCHIVE_BYTES,
    InvalidProjectArchive,
    ProjectTooLarge,
)
from app.analyzers.github.analyzer import (
    GitHubAPIError,
    GitHubNetworkError,
    GitHubProfileNotFound,
    GitHubRateLimitError,
    analyze_github_username,
)
from app.analyzers.coding.analyzer import analyze_coding_profiles
from app.analyzers.coding.errors import InvalidCodingUsername
from app.schemas.health import HealthResponse
from app.schemas.github import GitHubAnalysisRequest, GitHubAnalysisResponse
from app.schemas.coding import CodingAnalysisRequest, CodingAnalysisResponse
from app.schemas.project import ProjectAnalysisResponse
from app.schemas.resume import ResumeAnalysisResponse
from app.analyzers.kaggle.analyzer import (
    KaggleAPIError,
    KaggleNetworkError,
    KaggleProfileNotFound,
    KaggleRateLimitError,
    InvalidKaggleUsername,
    analyze_kaggle_username,
)
from app.schemas.kaggle import KaggleAnalysisRequest, KaggleAnalysisResponse
from app.analyzers.research.analyzer import analyze_research
from app.schemas.research import ResearchAnalysisRequest, ResearchAnalysisResponse
from app.analyzers.certifications.analyzer import analyze_certifications
from app.schemas.certifications import CertificationAnalysisRequest, CertificationAnalysisResponse
from app.analyzers.achievements.analyzer import analyze_achievements
from app.schemas.achievements import AchievementAnalysisRequest, AchievementAnalysisResponse
from app.ranking.feature_aggregator import aggregate_candidate
from app.ranking.schemas import CandidateAnalysisInputs, CandidateFeatureVector
from app.analyzers.resume.extractor import (
    EmptyResume,
    InvalidResumePDF,
    ResumeExtractionError,
    analyze_resume_text,
    extract_pdf_text,
)

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["health"])
def health_check() -> HealthResponse:
    """Report whether the AI service is accepting requests."""
    return HealthResponse(status="ok", service="beyondcv-ai")


@router.post("/analyze-resume", response_model=ResumeAnalysisResponse, tags=["resume"])
async def analyze_resume(file: UploadFile = File(..., description="PDF resume")) -> ResumeAnalysisResponse:
    """Extract explicitly stated resume facts from an uploaded PDF."""
    try:
        pdf_bytes = await file.read()
        text = extract_pdf_text(pdf_bytes)
        return analyze_resume_text(text)
    except InvalidResumePDF as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except EmptyResume as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ResumeExtractionError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        await file.close()


@router.post("/analyze-project", response_model=ProjectAnalysisResponse, tags=["project"])
async def analyze_project(file: UploadFile = File(..., description="ZIP archive containing a project")) -> ProjectAnalysisResponse:
    """Inspect source, documentation, and configuration in an uploaded ZIP without executing it."""
    try:
        archive_bytes = await file.read(MAX_ARCHIVE_BYTES + 1)
        if len(archive_bytes) > MAX_ARCHIVE_BYTES:
            raise HTTPException(status_code=413, detail="ZIP upload exceeds the analysis size limit.")
        return analyze_project_zip(archive_bytes)
    except InvalidProjectArchive as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ProjectTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    finally:
        await file.close()


@router.post("/analyze-github", response_model=GitHubAnalysisResponse, tags=["github"])
def analyze_github(request: GitHubAnalysisRequest) -> GitHubAnalysisResponse:
    """Analyze public GitHub profile evidence without treating popularity as ability."""
    try:
        return analyze_github_username(request.username)
    except GitHubProfileNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except GitHubRateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except GitHubNetworkError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except GitHubAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/analyze-coding", response_model=CodingAnalysisResponse, tags=["coding"])
def analyze_coding(request: CodingAnalysisRequest) -> CodingAnalysisResponse:
    """Analyze competitive-programming evidence from LeetCode and/or Codeforces."""
    try:
        return analyze_coding_profiles(
            leetcode_username=request.leetcode_username,
            codeforces_username=request.codeforces_username,
        )
    except InvalidCodingUsername as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/analyze-kaggle", response_model=KaggleAnalysisResponse, tags=["kaggle"])
def analyze_kaggle(request: KaggleAnalysisRequest) -> KaggleAnalysisResponse:
    """Collect bounded Kaggle notebook and dataset evidence for a username."""
    try:
        return analyze_kaggle_username(request.username)
    except InvalidKaggleUsername as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except KaggleProfileNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except KaggleRateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except KaggleNetworkError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except KaggleAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/analyze-research", response_model=ResearchAnalysisResponse, tags=["research"])
def analyze_research_route(request: ResearchAnalysisRequest) -> ResearchAnalysisResponse:
    """Structure and assess evidence completeness for candidate-supplied research."""
    return analyze_research(request)


@router.post("/analyze-certifications", response_model=CertificationAnalysisResponse, tags=["certifications"])
def analyze_certifications_route(request: CertificationAnalysisRequest) -> CertificationAnalysisResponse:
    """Normalize candidate-supplied certifications and optionally compare them to job text."""
    return analyze_certifications(request)


@router.post("/analyze-achievements", response_model=AchievementAnalysisResponse, tags=["achievements"])
def analyze_achievements_route(request: AchievementAnalysisRequest) -> AchievementAnalysisResponse:
    """Classify candidate-supplied competition and achievement outcomes as evidence."""
    return analyze_achievements(request)


@router.post("/aggregate-candidate", response_model=CandidateFeatureVector, tags=["feature aggregation"])
def aggregate_candidate_route(request: CandidateAnalysisInputs) -> CandidateFeatureVector:
    """Combine supplied analyzer responses into a normalized, evidence-linked feature vector."""
    return aggregate_candidate(request)
