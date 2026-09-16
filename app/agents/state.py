"""LangGraph state schema for the PDF-to-PPT conversion pipeline."""

from __future__ import annotations

from typing import Annotated, Any

from langgraph.graph import add_messages
from typing_extensions import TypedDict

from app.models.enums import JobStatus, PageStatus
from app.models.schemas import PageResult, SlideElement


class PageProcessingState(TypedDict):
    """State for processing a single page through the pipeline."""
    page_number: int
    page_image_path: str
    original_image_width: int
    original_image_height: int
    vlm_image_width: int       # Dimensions the VLM actually saw (after resize)
    vlm_image_height: int
    vlm_html_response: str
    parsed_elements: list[SlideElement]
    status: PageStatus
    error: str
    retry_count: int
    processing_time: float
    log_message: str


class PipelineState(TypedDict):
    """Top-level state for the entire conversion pipeline."""
    job_id: str
    pdf_path: str
    output_dir: str
    pptx_path: str
    total_pages: int
    processed_pages: int
    status: JobStatus

    # Per-page results (collected after parallel processing)
    page_results: list[PageResult]

    # Processing configuration
    dpi: int
    image_quality: int
    max_workers: int

    # Error tracking
    errors: list[str]

    # Current page being processed (for progress reporting)
    current_page: int
