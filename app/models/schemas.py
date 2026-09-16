"""Pydantic schemas for API request/response models and internal data structures."""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from app.models.enums import ElementType, JobStatus, PageStatus


# --- Slide Element Schemas ---

class BBox(BaseModel):
    """Bounding box in pixel coordinates (relative to source image)."""
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        return self.y2 - self.y1


class SlideElement(BaseModel):
    """A single element (text block or image region) to place on a PPT slide."""
    element_type: ElementType
    bbox: BBox
    text: str | None = None
    bold: bool = False
    italic: bool = False
    font_size_pt: int = 14
    alignment: str = "left"
    image_path: str | None = None  # Path to cropped image file


# --- Page Result ---

class PageResult(BaseModel):
    """Result of processing a single PDF page."""
    page_number: int
    status: PageStatus = PageStatus.PENDING
    elements: list[SlideElement] = Field(default_factory=list)
    processing_time_seconds: float = 0.0
    error_message: str | None = None
    log_message: str = ""


# --- Job Schemas ---

class JobRequest(BaseModel):
    """Request to start a PDF conversion job."""
    parallel_workers: int = Field(default=2, ge=1, le=5)
    dpi: int = Field(default=200, ge=100, le=400)
    image_quality: int = Field(default=85, ge=50, le=100)


class PageProgress(BaseModel):
    """Progress update for a single page."""
    page_number: int
    status: PageStatus
    message: str
    processing_time: float = 0.0


class JobProgress(BaseModel):
    """Overall job progress snapshot."""
    job_id: str
    status: JobStatus
    total_pages: int
    processed_pages: int
    current_page: int | None = None
    pages: list[PageProgress] = Field(default_factory=list)
    estimated_remaining_seconds: float | None = None
    pptx_available: bool = False
    output_path: str | None = None


class JobResponse(BaseModel):
    """Response when a conversion job is created."""
    job_id: str
    status: JobStatus
    total_pages: int
    message: str


# --- Internal Job State ---

class JobState(BaseModel):
    """Internal state for tracking a running job."""
    job_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    pdf_filename: str = ""
    pdf_path: str = ""
    total_pages: int = 0
    processed_pages: int = 0
    status: JobStatus = JobStatus.QUEUED
    page_results: list[PageResult] = Field(default_factory=list)
    output_dir: str = ""
    pptx_path: str = ""
    started_at: datetime | None = None
    completed_at: datetime | None = None
    errors: list[str] = Field(default_factory=list)

    # Processing settings
    parallel_workers: int = 2
    dpi: int = 200
    image_quality: int = 85
