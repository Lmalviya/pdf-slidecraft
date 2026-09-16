"""LangGraph workflow — orchestrates the full PDF-to-PPT conversion pipeline."""

from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pymupdf as fitz  # PyMuPDF

from app.agents.callbacks import ProgressTracker
from app.agents.nodes import process_single_page
from app.config import settings
from app.core.logging_config import get_logger
from app.models.enums import JobStatus, PageStatus
from app.models.schemas import JobState, PageResult
from app.services.pdf_service import PDFService
from app.services.ppt_service import PPTService
from app.services.storage_service import StorageService

logger = get_logger(__name__)

# Save interval: save intermediate PPT every N pages
INTERMEDIATE_SAVE_INTERVAL = 5


class ConversionPipeline:
    """Orchestrates the full PDF-to-PPT conversion.

    Manages:
    - PDF loading and page enumeration
    - Parallel page processing (configurable workers)
    - Progress tracking
    - Intermediate PPT saves
    - Final assembly and save
    """

    def __init__(self):
        self.pdf_service = PDFService()
        self.storage_service = StorageService()
        self.ppt_service: PPTService | None = None
        self.progress_tracker: ProgressTracker | None = None

    async def run(
        self,
        pdf_content: bytes,
        pdf_filename: str,
        parallel_workers: int = 2,
        dpi: int = 200,
        image_quality: int = 85,
        progress_tracker: ProgressTracker | None = None,
    ) -> JobState:
        """Execute the full conversion pipeline.

        Args:
            pdf_content: Raw PDF file bytes.
            pdf_filename: Original filename.
            parallel_workers: Number of concurrent page workers.
            dpi: Rendering DPI.
            image_quality: JPEG quality for cropped images.
            progress_tracker: Optional tracker for UI progress updates.

        Returns:
            JobState with results.
        """
        job = JobState(
            pdf_filename=pdf_filename,
            parallel_workers=parallel_workers,
            dpi=dpi,
            image_quality=image_quality,
        )
        job.status = JobStatus.PROCESSING
        job.started_at = __import__("datetime").datetime.now()

        self.progress_tracker = progress_tracker

        try:
            # Step 1: Create output directory
            output_dir, pptx_path = self.storage_service.create_job_directory(
                pdf_filename
            )
            job.output_dir = str(output_dir)
            job.pptx_path = str(pptx_path)

            # Step 2: Save uploaded PDF
            pdf_path = self.storage_service.save_uploaded_pdf(
                pdf_content, output_dir, pdf_filename
            )
            job.pdf_path = str(pdf_path)

            # Step 3: Load PDF
            doc = self.pdf_service.load_pdf(str(pdf_path))
            job.total_pages = doc.page_count

            if progress_tracker:
                progress_tracker.total_pages = job.total_pages

            logger.info(
                "pipeline_started",
                job_id=job.job_id,
                pages=job.total_pages,
                workers=parallel_workers,
            )

            # Step 4: Create presentation
            self.ppt_service = PPTService()
            self.ppt_service.create_presentation()

            # Step 5: Process pages sequentially (ordered output required)
            # We use an async semaphore to limit concurrency for VLM calls
            semaphore = asyncio.Semaphore(parallel_workers)
            page_results: dict[int, PageResult] = {}

            async def _process_with_semaphore(page_num: int) -> PageResult:
                async with semaphore:
                    return await process_single_page(
                        page_number=page_num,
                        doc=doc,
                        ppt_service=self.ppt_service,
                        output_dir=str(output_dir),
                        dpi=dpi,
                        progress_tracker=progress_tracker,
                    )

            # Process pages in order to maintain slide sequence
            # But allow limited concurrency for VLM calls
            for batch_start in range(0, job.total_pages, parallel_workers):
                batch_end = min(batch_start + parallel_workers, job.total_pages)
                batch_pages = list(range(batch_start, batch_end))

                # Run batch concurrently
                tasks = [_process_with_semaphore(p) for p in batch_pages]
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)

                # Collect results in order
                for page_num, result in zip(batch_pages, batch_results):
                    if isinstance(result, Exception):
                        logger.error(
                            "batch_page_exception",
                            page=page_num,
                            error=str(result),
                        )
                        page_results[page_num] = PageResult(
                            page_number=page_num,
                            status=PageStatus.FAILED,
                            error_message=str(result),
                            log_message=f"Exception: {result}",
                        )
                    else:
                        page_results[page_num] = result

                job.processed_pages = len(page_results)

                # Intermediate save every N pages
                if (
                    job.processed_pages % INTERMEDIATE_SAVE_INTERVAL == 0
                    or job.processed_pages == job.total_pages
                ):
                    try:
                        self.ppt_service.save_intermediate(str(pptx_path))
                    except Exception as e:
                        logger.warning("intermediate_save_failed", error=str(e))

            # Step 6: Final save
            self.ppt_service.save(str(pptx_path))

            # Collect results in page order
            job.page_results = [
                page_results[i]
                for i in sorted(page_results.keys())
            ]

            # Determine final status
            failed_count = sum(
                1 for r in job.page_results if r.status == PageStatus.FAILED
            )
            if failed_count == job.total_pages:
                job.status = JobStatus.FAILED
            else:
                job.status = JobStatus.COMPLETED

            job.completed_at = __import__("datetime").datetime.now()
            job.errors = [
                f"Page {r.page_number + 1}: {r.error_message}"
                for r in job.page_results
                if r.error_message
            ]

            doc.close()

            logger.info(
                "pipeline_completed",
                job_id=job.job_id,
                status=job.status,
                total=job.total_pages,
                completed=sum(
                    1 for r in job.page_results
                    if r.status in (PageStatus.COMPLETED, PageStatus.FALLBACK)
                ),
                failed=failed_count,
                pptx=str(pptx_path),
            )
            return job

        except Exception as e:
            job.status = JobStatus.FAILED
            job.errors.append(str(e))
            logger.error("pipeline_failed", job_id=job.job_id, error=str(e))
            return job
