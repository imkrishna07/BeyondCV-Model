"""Route registration for the service API."""

from fastapi import APIRouter
from fastapi import File, HTTPException, UploadFile

from app.analyzers.project.analyzer import analyze_project_zip
from app.analyzers.project.file_scanner import (
    MAX_ARCHIVE_BYTES,
    InvalidProjectArchive,
    ProjectTooLarge,
)
from app.schemas.health import HealthResponse
from app.schemas.project import ProjectAnalysisResponse
from app.schemas.resume import ResumeAnalysisResponse
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
