"""HTML parser service — extracts structured elements from QwenVL HTML output."""

from __future__ import annotations

import json
import re

from bs4 import BeautifulSoup, Tag

from app.core.exceptions import HTMLParsingError
from app.core.logging_config import get_logger
from app.models.enums import ElementType
from app.models.schemas import BBox, SlideElement

logger = get_logger(__name__)

# Map HTML tags to element types
TAG_TYPE_MAP = {
    "h1": ElementType.HEADING,
    "h2": ElementType.SUBHEADING,
    "h3": ElementType.SUBHEADING,
    "h4": ElementType.SUBHEADING,
    "h5": ElementType.SUBHEADING,
    "h6": ElementType.SUBHEADING,
    "p": ElementType.PARAGRAPH,
    "li": ElementType.BULLET,
    "img": ElementType.IMAGE,
    "table": ElementType.TABLE,
    "td": ElementType.PARAGRAPH,
    "th": ElementType.HEADING,
    "blockquote": ElementType.PARAGRAPH,
}

# Map element types to default font sizes
FONT_SIZE_MAP = {
    ElementType.HEADING: 26,
    ElementType.SUBHEADING: 20,
    ElementType.PARAGRAPH: 14,
    ElementType.BULLET: 14,
    ElementType.CAPTION: 12,
    ElementType.TABLE: 12,
}


class HTMLParserService:
    """Parses QwenVL HTML output into structured SlideElement objects."""

    def parse(self, html_content: str, default_width: int = 512, default_height: int = 660) -> list[SlideElement]:
        """Parse VLM HTML response into a list of SlideElements.

        Args:
            html_content: Raw HTML or text string from the VLM.
            default_width: Image width (for synthetic layout calculation if bbox missing).
            default_height: Image height.

        Returns:
            List of SlideElement objects with type, bbox, text/image info.
        """
        if not html_content or not html_content.strip():
            logger.warning("html_parse_empty_content")
            return []

        try:
            cleaned = self._clean_html(html_content)
            soup = BeautifulSoup(cleaned, "html.parser")
            raw_elements: list[SlideElement] = []

            # 1. First pass: try to find structured semantic tags
            target_tags = ["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "td", "th", "blockquote", "img", "div", "figure"]
            found_tags = soup.find_all(target_tags)

            for tag in found_tags:
                element = self._process_tag(tag)
                if element:
                    raw_elements.append(element)

            # 2. If soup produced no elements (e.g. raw text / markdown output), fallback to text block parsing
            if not raw_elements:
                raw_elements = self._parse_fallback_text(cleaned)

            if not raw_elements:
                logger.warning("no_elements_extracted_from_html", raw_preview=cleaned[:200])
                return []

            # 3. Deduplicate elements
            elements = self._deduplicate(raw_elements)

            # 4. Fill in missing bounding boxes with vertical flow layout
            elements = self._assign_flow_bboxes(elements, default_width, default_height)

            logger.info(
                "html_parsed_successfully",
                total_elements=len(elements),
                text_count=sum(1 for e in elements if e.element_type != ElementType.IMAGE),
                image_count=sum(1 for e in elements if e.element_type == ElementType.IMAGE),
            )
            return elements

        except Exception as e:
            logger.error("html_parse_unexpected_error", error=str(e), exc_info=True)
            fallback = self._parse_fallback_text(html_content)
            if fallback:
                return self._assign_flow_bboxes(fallback, default_width, default_height)
            return []

    def parse_html_to_elements(self, html_content: str, default_width: int = 512, default_height: int = 660) -> list[SlideElement]:
        """Convenience alias for parse()."""
        return self.parse(html_content, default_width=default_width, default_height=default_height)

    def _clean_html(self, html: str) -> str:
        """Clean common VLM output artifacts."""
        html = re.sub(r"^```html?\s*", "", html, flags=re.IGNORECASE | re.MULTILINE)
        html = re.sub(r"```\s*$", "", html, flags=re.MULTILINE)
        return html.strip()

    def _process_tag(self, tag: Tag) -> SlideElement | None:
        """Process a single HTML tag into a SlideElement."""
        tag_name = tag.name.lower() if tag.name else ""

        # Skip container-only tags
        if tag_name in ("ul", "ol", "table", "tbody", "thead", "tr", "html", "body", "head"):
            return None

        classes = tag.get("class", [])
        if isinstance(classes, str):
            classes = classes.split()

        # Check for image div or img tag
        is_image = tag_name == "img" or "image" in classes or tag_name == "figure"
        if is_image:
            bbox = self._parse_bbox(tag)
            alt = tag.get("alt") or tag.get("data-alt") or "image_region"
            return SlideElement(
                element_type=ElementType.IMAGE,
                bbox=bbox or BBox(x1=0, y1=0, x2=100, y2=100),
                text=str(alt),
            )

        # For normal divs, only process if they have direct text and are not generic wrappers
        if tag_name == "div" and not tag.get("data-bbox"):
            return None

        element_type = TAG_TYPE_MAP.get(tag_name, ElementType.PARAGRAPH)

        # Extract text content
        text = tag.get_text(separator=" ", strip=True)
        if not text:
            return None

        # Detect formatting
        bold = bool(tag.find(["b", "strong"]) or tag_name in ("h1", "h2"))
        italic = bool(tag.find(["i", "em"]))
        font_size = FONT_SIZE_MAP.get(element_type, 14)

        # Detect alignment from style
        alignment = "left"
        style = str(tag.get("style", ""))
        if "text-align: center" in style or "text-align:center" in style:
            alignment = "center"
        elif "text-align: right" in style or "text-align:right" in style:
            alignment = "right"

        bbox = self._parse_bbox(tag)

        return SlideElement(
            element_type=element_type,
            bbox=bbox or BBox(x1=0, y1=0, x2=100, y2=100),
            text=text,
            bold=bold,
            italic=italic,
            font_size_pt=font_size,
            alignment=alignment,
        )

    def _parse_bbox(self, tag: Tag) -> BBox | None:
        """Extract data-bbox attribute and parse into BBox object.
        Supports [ymin, xmin, ymax, xmax] standard VLM coordinate order or [x1, y1, x2, y2].
        """
        raw = tag.get("data-bbox") or tag.get("bbox") or tag.get("box") or tag.get("data_bbox")
        if not raw:
            return None

        try:
            if isinstance(raw, str):
                cleaned_str = re.sub(r"[\[\]\(\)\s]", "", raw)
                coords = [float(c) for c in cleaned_str.split(",") if c]
            elif isinstance(raw, (list, tuple)):
                coords = [float(c) for c in raw]
            else:
                return None

            if len(coords) != 4:
                return None

            # Standard VLM output order is [ymin, xmin, ymax, xmax]
            # Convert to [x1, y1, x2, y2]
            c0, c1, c2, c3 = coords
            if c0 <= 1000 and c1 <= 1000 and c2 <= 1000 and c3 <= 1000:
                # If in [ymin, xmin, ymax, xmax] order (where y1=c0, x1=c1, y2=c2, x2=c3)
                y1, x1, y2, x2 = c0, c1, c2, c3
            else:
                x1, y1, x2, y2 = c0, c1, c2, c3

            # Ensure valid bounds
            if x2 < x1:
                x1, x2 = x2, x1
            if y2 < y1:
                y1, y2 = y2, y1

            if x2 == x1 or y2 == y1:
                return None

            return BBox(x1=x1, y1=y1, x2=x2, y2=y2)

        except Exception:
            return None

    def _parse_fallback_text(self, text: str) -> list[SlideElement]:
        """Fallback parser if VLM returns plain text or Markdown instead of HTML."""
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        elements: list[SlideElement] = []

        for line in lines:
            if line.startswith("#"):
                clean_text = line.lstrip("#").strip()
                elements.append(
                    SlideElement(
                        element_type=ElementType.HEADING,
                        bbox=BBox(x1=0, y1=0, x2=100, y2=100),
                        text=clean_text,
                        bold=True,
                        font_size_pt=24,
                    )
                )
            elif line.startswith(("-", "*", "•", "1.", "2.", "3.")):
                clean_text = re.sub(r"^[-*•\d.]+\s*", "", line).strip()
                elements.append(
                    SlideElement(
                        element_type=ElementType.BULLET,
                        bbox=BBox(x1=0, y1=0, x2=100, y2=100),
                        text=clean_text,
                        font_size_pt=14,
                    )
                )
            else:
                elements.append(
                    SlideElement(
                        element_type=ElementType.PARAGRAPH,
                        bbox=BBox(x1=0, y1=0, x2=100, y2=100),
                        text=line,
                        font_size_pt=14,
                    )
                )

        return elements

    def _assign_flow_bboxes(
        self, elements: list[SlideElement], width: int, height: int
    ) -> list[SlideElement]:
        """Assign sequential vertical flow bounding boxes to elements missing explicit coordinates."""
        total = len(elements)
        if total == 0:
            return elements

        margin_x = width * 0.08
        content_width = width * 0.84
        top_y = height * 0.08
        available_height = height * 0.84

        curr_y = top_y
        row_height = available_height / max(total, 1)

        for el in elements:
            if el.bbox.x1 == 0 and el.bbox.y1 == 0 and el.bbox.x2 == 100 and el.bbox.y2 == 100:
                el_h = min(row_height * 0.85, 80 if el.element_type == ElementType.HEADING else 45)
                el.bbox = BBox(
                    x1=margin_x,
                    y1=curr_y,
                    x2=margin_x + content_width,
                    y2=curr_y + el_h,
                )
                curr_y += row_height
            else:
                if el.bbox.x2 <= 1000 and el.bbox.y2 <= 1000 and width > 1000:
                    scale_x = width / 1000.0
                    scale_y = height / 1000.0
                    el.bbox = BBox(
                        x1=el.bbox.x1 * scale_x,
                        y1=el.bbox.y1 * scale_y,
                        x2=el.bbox.x2 * scale_x,
                        y2=el.bbox.y2 * scale_y,
                    )

        return elements

    def _deduplicate(self, elements: list[SlideElement]) -> list[SlideElement]:
        """Remove duplicate elements."""
        seen: set[str] = set()
        unique: list[SlideElement] = []

        for el in elements:
            key_text = (el.text or "").strip().lower()[:60]
            if not key_text and el.element_type != ElementType.IMAGE:
                continue
            key = f"{el.element_type}_{key_text}"
            if key not in seen:
                seen.add(key)
                unique.append(el)

        return unique
