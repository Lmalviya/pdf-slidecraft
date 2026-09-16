"""Local OCR Service using RapidOCR (ONNX Runtime).

Provides ultra-fast, highly accurate text line detection with exact bounding boxes
running locally on CPU in ~0.2-0.4s per page.
"""

from __future__ import annotations

import numpy as np
from PIL import Image
from rapidocr_onnxruntime import RapidOCR

from app.core.logging_config import get_logger
from app.models.schemas import BBox

logger = get_logger(__name__)


class OCRTextLine:
    """Represents a single line of text detected by OCR."""

    def __init__(self, text: str, bbox: BBox, confidence: float):
        self.text = text
        self.bbox = bbox
        self.confidence = confidence

    @property
    def font_size_estimate(self) -> int:
        """Estimate font size in points from bounding box height."""
        height = self.bbox.height
        # At 200 DPI, 1 pt is ~2.78 pixels (200 / 72)
        # Approximate: pt = pixel_height * 0.75
        estimated = max(10, min(int(height * 0.75), 48))
        return estimated

    def __repr__(self) -> str:
        return f"OCRTextLine(text='{self.text}', bbox={self.bbox}, conf={self.confidence:.2f})"


class OCRService:
    """Wrapper around RapidOCR for document text extraction."""

    def __init__(self):
        # Initialize RapidOCR with CPU execution
        self.engine = RapidOCR()
        logger.info("ocr_service_initialized")

    def extract_text_lines(self, image: Image.Image) -> list[OCRTextLine]:
        """Extract all text lines and bounding boxes from an image.

        Args:
            image: PIL Image of the rendered document page.

        Returns:
            List of OCRTextLine objects with text, bbox, and confidence.
        """
        # Convert PIL Image to numpy array (RGB)
        if image.mode != "RGB":
            image = image.convert("RGB")
        img_np = np.array(image)

        # RapidOCR returns (results, elapse)
        # result: list of [box, text, score]
        # box is [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
        results, _ = self.engine(img_np)

        if not results:
            logger.info("ocr_no_text_detected")
            return []

        lines: list[OCRTextLine] = []
        for item in results:
            box, text, score = item
            if not text or not str(text).strip() or float(score) < 0.35:
                continue

            # Convert 4-point polygon to axis-aligned bounding box
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            x1, y1 = max(0, min(xs)), max(0, min(ys))
            x2, y2 = min(image.width, max(xs)), min(image.height, max(ys))

            if x2 <= x1 or y2 <= y1:
                continue

            bbox = BBox(x1=float(x1), y1=float(y1), x2=float(x2), y2=float(y2))
            lines.append(OCRTextLine(text=str(text).strip(), bbox=bbox, confidence=float(score)))

        logger.info(
            "ocr_extraction_complete",
            lines_detected=len(lines),
            image_size=f"{image.width}x{image.height}",
        )
        return lines
