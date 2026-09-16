"""LangGraph node functions — each node is a step in the page processing pipeline."""

from __future__ import annotations

import time
from pathlib import Path

from PIL import Image

from app.agents.callbacks import PageUpdate, ProgressTracker
from app.config import settings
from app.core.exceptions import (
    PDFRenderError,
)
from app.core.logging_config import get_logger
from app.models.enums import ElementType, PageStatus, ProcessingEngine
from app.models.schemas import BBox, PageResult, SlideElement
from app.services.html_parser_service import HTMLParserService
from app.services.layout_service import LayoutService
from app.services.nvidia_service import NvidiaVisionService
from app.services.ocr_service import OCRService
from app.services.pdf_service import PDFService
from app.services.ppt_service import PPTService
from app.services.vlm_service import VLMService

logger = get_logger(__name__)

# Shared service instances
pdf_service = PDFService()
ocr_service = OCRService()
layout_service = LayoutService()
html_parser_service = HTMLParserService()


async def process_single_page(
    page_number: int,
    doc,
    ppt_service: PPTService,
    output_dir: str,
    dpi: int = 150,
    engine: ProcessingEngine = ProcessingEngine.LOCAL_OCR,
    nvidia_service: NvidiaVisionService | None = None,
    vlm_service: VLMService | None = None,
    progress_tracker: ProgressTracker | None = None,
) -> PageResult:
    """Process a single PDF page through the selected engine (Local OCR, NVIDIA API, or Local VLM).

    Features:
    - Digital text fast path (instant vector text when available)
    - Engine routing: Local RapidOCR, NVIDIA Cloud Vision API, or Ollama VLM
    - Automatic fallback: If cloud API fails, gracefully falls back to Local OCR
    - Structured slide generation with cropped pictures and formatted text
    """
    start_time = time.time()
    result = PageResult(page_number=page_number)

    def _report(status: PageStatus, msg: str):
        elapsed = time.time() - start_time
        if progress_tracker:
            progress_tracker.update_page(
                PageUpdate(
                    page_number=page_number,
                    status=status,
                    message=msg,
                    processing_time=elapsed,
                )
            )

    try:
        # Step 1: Render page to high-res image
        _report(PageStatus.RENDERING, f"Rendering page {page_number + 1} at {dpi} DPI...")
        render_start = time.time()
        page_image = pdf_service.render_page_to_image(doc, page_number, dpi=dpi)
        render_dur = round(time.time() - render_start, 2)
        orig_w, orig_h = page_image.width, page_image.height

        # Step 2: Check for native digital vector text first (fastest & 100% exact)
        digital_elements, page_w, page_h = pdf_service.extract_page_digital_elements(doc, page_number)
        has_digital_text = sum(1 for e in digital_elements if e.element_type != ElementType.IMAGE) >= 2

        if has_digital_text:
            _report(PageStatus.BUILDING, f"Extracting {len(digital_elements)} native text/image elements...")
            ppt_start = time.time()
            ppt_service.add_slide_from_elements(
                elements=digital_elements,
                page_image=page_image,
                page_number=page_number,
                image_width=page_w,
                image_height=page_h,
            )
            ppt_dur = round(time.time() - ppt_start, 2)
            elapsed = round(time.time() - start_time, 2)

            text_count = sum(1 for e in digital_elements if e.element_type != ElementType.IMAGE)
            image_count = sum(1 for e in digital_elements if e.element_type == ElementType.IMAGE)

            result.status = PageStatus.COMPLETED
            result.elements = digital_elements
            result.duration_s = elapsed
            result.text_elements_count = text_count
            result.image_elements_count = image_count
            result.log_message = f"{text_count} text blocks, {image_count} images (vector text)"
            _report(PageStatus.COMPLETED, f"Completed in {elapsed}s: {result.log_message}")

            logger.info(
                "page_processed_via_digital_extract",
                page=page_number + 1,
                text_count=text_count,
                image_count=image_count,
                total_duration_s=elapsed,
            )
            return result

        # Step 3: Process via Selected Engine
        elements: list[SlideElement] = []
        engine_used = engine.value

        # --- A. NVIDIA NIM Cloud Vision Engine ---
        if engine == ProcessingEngine.NVIDIA_API and nvidia_service:
            try:
                _report(PageStatus.ANALYZING, f"Sending page {page_number + 1} to NVIDIA NIM ({nvidia_service.model})...")
                nv_start = time.time()
                raw_html = await nvidia_service.analyze_slide_image(page_image, page_number=page_number)
                nv_dur = round(time.time() - nv_start, 2)

                _report(PageStatus.PARSING, f"Parsing NVIDIA layout structure...")
                elements = html_parser_service.parse_html_to_elements(raw_html, orig_w, orig_h)
                logger.info("page_processed_via_nvidia", page=page_number + 1, duration_s=nv_dur, elements=len(elements))
            except Exception as nv_err:
                logger.warning(
                    "nvidia_api_failed_falling_back",
                    page=page_number + 1,
                    error=str(nv_err),
                    fallback="local_ocr",
                )
                _report(PageStatus.ANALYZING, f"NVIDIA API unavailable ({nv_err}), falling back to Local OCR...")
                engine_used = "local_ocr_fallback"

        # --- B. Local Ollama VLM Engine ---
        elif engine == ProcessingEngine.LOCAL_VLM and vlm_service:
            try:
                _report(PageStatus.ANALYZING, f"Sending page {page_number + 1} to Ollama ({vlm_service.model_name})...")
                vlm_start = time.time()
                raw_html = await vlm_service.analyze_page_layout(page_image, page_number=page_number)
                vlm_dur = round(time.time() - vlm_start, 2)

                _report(PageStatus.PARSING, f"Parsing VLM layout structure...")
                elements = html_parser_service.parse_html_to_elements(raw_html, orig_w, orig_h)
                logger.info("page_processed_via_ollama", page=page_number + 1, duration_s=vlm_dur, elements=len(elements))
            except Exception as vlm_err:
                logger.warning(
                    "ollama_vlm_failed_falling_back",
                    page=page_number + 1,
                    error=str(vlm_err),
                    fallback="local_ocr",
                )
                _report(PageStatus.ANALYZING, f"Ollama VLM failed ({vlm_err}), falling back to Local OCR...")
                engine_used = "local_ocr_fallback"

        # --- C. Local Fast RapidOCR + OpenCV Layout Engine (Primary or Fallback) ---
        if not elements:
            _report(PageStatus.ANALYZING, f"Running RapidOCR and Layout Detection on page {page_number + 1}...")
            ocr_start = time.time()
            ocr_lines = ocr_service.extract_text_lines(page_image)
            ocr_dur = round(time.time() - ocr_start, 2)

            _report(PageStatus.PARSING, f"Detecting image regions and structuring layout ({len(ocr_lines)} text lines)...")
            layout_start = time.time()
            elements = layout_service.analyze_page(page_image, ocr_lines)
            layout_dur = round(time.time() - layout_start, 2)

        if not elements:
            # Fallback if page is completely blank or unreadable
            _report(PageStatus.FALLBACK, f"No elements detected on page {page_number + 1}, inserting full-page image")
            ppt_service.add_full_page_image_slide(page_image, page_number)
            elapsed = round(time.time() - start_time, 2)
            result.status = PageStatus.FALLBACK
            result.duration_s = elapsed
            result.log_message = "No elements detected, added as full-page image"
            return result

        # Step 4: Build PPT slide with cropped photos and editable text boxes
        text_count = sum(1 for e in elements if e.element_type != ElementType.IMAGE)
        image_count = sum(1 for e in elements if e.element_type == ElementType.IMAGE)
        _report(PageStatus.BUILDING, f"Creating PPT slide ({text_count} text blocks, {image_count} photos/diagrams)...")

        ppt_start = time.time()
        ppt_service.add_slide_from_elements(
            elements=elements,
            page_image=page_image,
            page_number=page_number,
            image_width=orig_w,
            image_height=orig_h,
        )
        ppt_dur = round(time.time() - ppt_start, 2)

        elapsed = round(time.time() - start_time, 2)
        result.status = PageStatus.COMPLETED
        result.elements = elements
        result.duration_s = elapsed
        result.text_elements_count = text_count
        result.image_elements_count = image_count
        result.log_message = f"{text_count} text blocks, {image_count} images/diagrams via {engine_used}"
        _report(PageStatus.COMPLETED, f"Completed in {elapsed}s: {result.log_message}")

        logger.info(
            "page_processed_successfully",
            page=page_number + 1,
            engine=engine_used,
            text_count=text_count,
            image_count=image_count,
            render_s=render_dur,
            ppt_s=ppt_dur,
            total_duration_s=elapsed,
        )
        return result

    except PDFRenderError as e:
        elapsed = round(time.time() - start_time, 2)
        result.status = PageStatus.FAILED
        result.duration_s = elapsed
        result.error_message = str(e)
        result.log_message = f"PDF rendering failed: {e}"
        _report(PageStatus.FAILED, result.log_message)
        logger.error("page_render_failed", page=page_number + 1, error=str(e))
        return result

    except Exception as e:
        elapsed = round(time.time() - start_time, 2)
        logger.error("page_unexpected_failure", page=page_number + 1, error=str(e), exc_info=True)

        try:
            page_image = pdf_service.render_page_to_image(doc, page_number, dpi=dpi)
            ppt_service.add_full_page_image_slide(page_image, page_number)
        except Exception:
            pass

        result.status = PageStatus.FALLBACK
        result.duration_s = elapsed
        result.error_message = str(e)
        result.log_message = f"Processing error ({e}), inserted as full-page image"
        _report(PageStatus.FALLBACK, result.log_message)
        return result

