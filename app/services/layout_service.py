"""Layout Analysis Service — detects image/diagram regions and groups text into structured slide elements."""

from __future__ import annotations

import re
import cv2
import numpy as np
from PIL import Image

from app.core.logging_config import get_logger
from app.models.enums import ElementType
from app.models.schemas import BBox, SlideElement
from app.services.ocr_service import OCRTextLine

logger = get_logger(__name__)

# Regex for detecting bullet points and numbered lists
BULLET_REGEX = re.compile(
    r"^([•\-\*■◆○●►–—]|(\d+[\.\)])|([a-zA-Z][\.\)])|(\([a-zA-Z0-9]+\))|([ivxIVX]+[\.\)]))\s*"
)


class LayoutService:
    """Analyzes page layout, detects non-text images/diagrams, and groups text lines into slide blocks."""

    def analyze_page(
        self,
        image: Image.Image,
        ocr_lines: list[OCRTextLine],
    ) -> list[SlideElement]:
        """Perform full layout analysis on a document page.

        Args:
            image: High-res PIL Image of the rendered PDF page.
            ocr_lines: List of OCR text lines detected on the page.

        Returns:
            List of structured SlideElement objects (headings, bullets, paragraphs, images).
        """
        elements: list[SlideElement] = []

        # 1. Detect and extract non-text image/photo/diagram regions
        image_bboxes = self.detect_image_regions(image, ocr_lines)
        for i, img_box in enumerate(image_bboxes):
            elements.append(
                SlideElement(
                    element_type=ElementType.IMAGE,
                    bbox=img_box,
                    text=f"image_region_{i + 1}",
                )
            )

        # 2. Group text lines into semantic blocks (headings, bullets, paragraphs)
        text_elements = self.group_text_lines(ocr_lines, image.width, image.height, image_bboxes)
        elements.extend(text_elements)

        logger.info(
            "layout_analysis_complete",
            images_found=len(image_bboxes),
            text_blocks=len(text_elements),
            total_elements=len(elements),
        )
        return elements

    def detect_image_regions(
        self,
        image: Image.Image,
        ocr_lines: list[OCRTextLine],
    ) -> list[BBox]:
        """Detect photos, diagrams, and illustrations using edge morphology and texture analysis."""
        if image.mode != "RGB":
            image = image.convert("RGB")
        img_np = np.array(image)
        h, w = img_np.shape[:2]

        # 1. Create a mask covering all text regions
        text_mask = np.zeros((h, w), dtype=np.uint8)
        for line in ocr_lines:
            b = line.bbox
            pad_x = 12
            pad_y = 10
            x1 = max(0, int(b.x1) - pad_x)
            y1 = max(0, int(b.y1) - pad_y)
            x2 = min(w, int(b.x2) + pad_x)
            y2 = min(h, int(b.y2) + pad_y)
            cv2.rectangle(text_mask, (x1, y1), (x2, y2), 255, -1)

        # 2. Edge detection on non-text regions (robust to smooth background gradients)
        gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 25, 90)
        edges[text_mask > 0] = 0  # Exclude text edges

        # 3. Morphological dilation to fuse photo/diagram components
        kernel_dilate = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
        dilated = cv2.dilate(edges, kernel_dilate, iterations=3)
        kernel_close = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 25))
        closed = cv2.morphologyEx(dilated, cv2.MORPH_CLOSE, kernel_close)

        # 4. Find external contours
        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        image_bboxes: list[BBox] = []
        min_dim = min(w, h) * 0.08  # At least 8% of page dimension
        min_area = (w * h) * 0.015  # At least 1.5% of total slide area

        for cnt in contours:
            x, y, cw, ch = cv2.boundingRect(cnt)
            area = cw * ch

            # Filter out tiny icons or entire page border
            if cw < min_dim or ch < min_dim or area < min_area:
                continue

            # Filter out full-width top/bottom decorative header/footer bars
            if cw > w * 0.85 and (y < h * 0.12 or y + ch > h * 0.88):
                continue

            if cw > w * 0.95 and ch > h * 0.95:
                continue

            # Standard deviation check: ensure it's not a solid flat color block
            roi = img_np[y : y + ch, x : x + cw]
            if roi.size == 0:
                continue

            std_dev = float(np.mean(np.std(roi, axis=(0, 1))))
            if std_dev < 12.0:
                continue

            box = BBox(x1=float(x), y1=float(y), x2=float(x + cw), y2=float(y + ch))
            image_bboxes.append(box)

        # Merge overlapping/adjacent boxes
        return self._merge_overlapping_boxes(image_bboxes)

    def group_text_lines(
        self,
        ocr_lines: list[OCRTextLine],
        page_width: int,
        page_height: int,
        image_bboxes: list[BBox],
    ) -> list[SlideElement]:
        """Group individual OCR lines into structured slide elements (headings, bullet lists, paragraphs)."""
        if not ocr_lines:
            return []

        # 1. Merge text lines that lie on the same horizontal row with small horizontal gap
        merged_rows = self._merge_same_row_lines(ocr_lines)

        # Sort lines reading order (top-to-bottom, left-to-right)
        sorted_lines = sorted(merged_rows, key=lambda l: (round(l.bbox.y1 / 25) * 25, l.bbox.x1))

        # 2. Identify Heading / Title (prominent position at top)
        max_height = max(l.bbox.height for l in sorted_lines)
        elements: list[SlideElement] = []

        title_candidates = [
            l for l in sorted_lines
            if l.bbox.y1 < page_height * 0.35 and (l.bbox.height >= max_height * 0.75 or l.text.isupper())
        ]

        title_line = title_candidates[0] if title_candidates else None
        if title_line and (title_line.bbox.height >= 18 or title_line.bbox.y1 < page_height * 0.25):
            elements.append(
                SlideElement(
                    element_type=ElementType.HEADING,
                    bbox=title_line.bbox,
                    text=title_line.text,
                    bold=True,
                    font_size_pt=max(22, title_line.font_size_estimate),
                    alignment="left",
                )
            )
            remaining_lines = [l for l in sorted_lines if l != title_line]
        else:
            remaining_lines = sorted_lines

        # 3. Process remaining lines into structured bullet lists and paragraphs
        current_block_lines: list[OCRTextLine] = []

        def flush_block():
            if not current_block_lines:
                return

            full_text = "\n".join(l.text for l in current_block_lines)
            min_x = min(l.bbox.x1 for l in current_block_lines)
            min_y = min(l.bbox.y1 for l in current_block_lines)
            max_x = max(l.bbox.x2 for l in current_block_lines)
            max_y = max(l.bbox.y2 for l in current_block_lines)

            first_line = current_block_lines[0].text
            is_bullet = bool(BULLET_REGEX.match(first_line)) or any(
                BULLET_REGEX.match(l.text) for l in current_block_lines
            )

            el_type = ElementType.BULLET if is_bullet else ElementType.PARAGRAPH
            avg_font = int(np.mean([l.font_size_estimate for l in current_block_lines]))

            elements.append(
                SlideElement(
                    element_type=el_type,
                    bbox=BBox(x1=min_x, y1=min_y, x2=max_x, y2=max_y),
                    text=full_text,
                    font_size_pt=max(12, min(avg_font, 20)),
                    alignment="left",
                )
            )
            current_block_lines.clear()

        for line in remaining_lines:
            if not current_block_lines:
                current_block_lines.append(line)
                continue

            prev_line = current_block_lines[-1]
            vertical_gap = line.bbox.y1 - prev_line.bbox.y2
            line_h = max(line.bbox.height, prev_line.bbox.height, 15)

            is_new_bullet = bool(BULLET_REGEX.match(line.text))
            is_large_gap = vertical_gap > line_h * 1.8

            if is_new_bullet or is_large_gap:
                flush_block()
                current_block_lines.append(line)
            else:
                current_block_lines.append(line)

        flush_block()
        return elements

    def _merge_same_row_lines(self, lines: list[OCRTextLine]) -> list[OCRTextLine]:
        """Merge OCR text fragments that lie on the same horizontal line and are close horizontally."""
        if not lines:
            return []

        sorted_lines = sorted(lines, key=lambda l: (l.bbox.y1, l.bbox.x1))
        merged: list[OCRTextLine] = []
        used: set[int] = set()

        for i, l1 in enumerate(sorted_lines):
            if i in used:
                continue
            same_row = [l1]
            used.add(i)

            for j, l2 in enumerate(sorted_lines):
                if j in used:
                    continue
                # Check vertical overlap
                y_overlap = min(l1.bbox.y2, l2.bbox.y2) - max(l1.bbox.y1, l2.bbox.y1)
                min_h = min(l1.bbox.height, l2.bbox.height)
                if y_overlap > min_h * 0.45:
                    # Check horizontal proximity (avoid joining distant columns)
                    gap_x = max(0, min(l1.bbox.x2, l2.bbox.x2) - max(l1.bbox.x1, l2.bbox.x1))
                    dist_x = max(0, max(l1.bbox.x1, l2.bbox.x1) - min(l1.bbox.x2, l2.bbox.x2))
                    if dist_x < min_h * 3.5:
                        same_row.append(l2)
                        used.add(j)

            # Sort fragments in this row from left to right
            same_row.sort(key=lambda l: l.bbox.x1)
            combined_text = " ".join(l.text for l in same_row)
            min_x = min(l.bbox.x1 for l in same_row)
            min_y = min(l.bbox.y1 for l in same_row)
            max_x = max(l.bbox.x2 for l in same_row)
            max_y = max(l.bbox.y2 for l in same_row)
            avg_font = int(np.mean([l.font_size_estimate for l in same_row]))
            min_conf = min(l.confidence for l in same_row)

            merged.append(
                OCRTextLine(
                    text=combined_text,
                    bbox=BBox(x1=min_x, y1=min_y, x2=max_x, y2=max_y),
                    confidence=min_conf,
                )
            )

        return merged

    def _merge_overlapping_boxes(self, boxes: list[BBox]) -> list[BBox]:
        """Merge bounding boxes that overlap significantly."""
        if not boxes:
            return []

        merged: list[BBox] = []
        for box in boxes:
            matched = False
            for i, m in enumerate(merged):
                if (
                    box.x1 <= m.x2 + 25 and box.x2 >= m.x1 - 25
                    and box.y1 <= m.y2 + 25 and box.y2 >= m.y1 - 25
                ):
                    merged[i] = BBox(
                        x1=min(box.x1, m.x1),
                        y1=min(box.y1, m.y1),
                        x2=max(box.x2, m.x2),
                        y2=max(box.y2, m.y2),
                    )
                    matched = True
                    break
            if not matched:
                merged.append(box)

        return merged
