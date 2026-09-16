"""Conversion API routes — upload, progress, download."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.core.logging_config import get_logger
from app.models.enums import JobStatus
from app.models.schemas import JobState

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1", tags=["conversion"])

# In-memory job store (single-user app — sufficient for this use case)
_active_jobs: dict[str, JobState] = {}


def register_job(job: JobState) -> None:
    """Register a job in the store."""
    _active_jobs[job.job_id] = job


def get_job(job_id: str) -> JobState | None:
    """Get a job by ID."""
    return _active_jobs.get(job_id)


@router.get("/jobs/{job_id}/status")
async def job_status(job_id: str) -> dict:
    """Get current job status."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    return {
        "job_id": job.job_id,
        "status": job.status,
        "total_pages": job.total_pages,
        "processed_pages": job.processed_pages,
        "pptx_available": Path(job.pptx_path).exists() if job.pptx_path else False,
        "output_dir": job.output_dir,
        "errors": job.errors,
    }


@router.get("/jobs/{job_id}/download")
async def download_pptx(job_id: str):
    """Download the generated PPTX file."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    if not job.pptx_path or not Path(job.pptx_path).exists():
        raise HTTPException(
            status_code=404, detail="PPTX file not yet available"
        )

    return FileResponse(
        path=job.pptx_path,
        filename=Path(job.pptx_path).name,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )
