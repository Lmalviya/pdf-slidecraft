"""PDF processing service — renders PDF pages to images using PyMuPDF."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pymupdf as fitz  # PyMuPDF
from PIL import Image

from app.core.exceptions import PDFLoadError, PDFRenderError
from app.core.logging_config import get_logger

if TYPE_CHECKING:
    from app.models.schemas import SlideElement

logger = get_logger(__name__)


class PDFService:
    """Handles PDF loading and page-to-image rendering."""

    def load_pdf(self, pdf_path: str) -> fitz.Document:
        """Load a PDF file and return the document object.

        Raises:
            PDFLoadError: If the file cannot be opened or is not a valid PDF.
        """
        path = Path(pdf_path)
        if not path.exists():
            raise PDFLoadError(f"PDF file not found: {pdf_path}")
        if not path.suffix.lower() == ".pdf":
            raise PDFLoadError(f"Not a PDF file: {pdf_path}")

        try:
            doc = fitz.open(pdf_path)
            if doc.page_count == 0:
                raise PDFLoadError(f"PDF has no pages: {pdf_path}")
            logger.info("pdf_loaded", path=pdf_path, pages=doc.page_count)
            return doc
        except fitz.FileDataError as e:
            raise PDFLoadError(f"Invalid or corrupted PDF: {pdf_path}") from e
        except Exception as e:
            raise PDFLoadError(f"Failed to load PDF: {e}") from e

    def get_page_count(self, doc: fitz.Document) -> int:
        """Return the number of pages in the document."""
        return doc.page_count

    def render_page_to_image(
        self,
        doc: fitz.Document,
        page_number: int,
        dpi: int = 200,
        output_path: str | None = None,
    ) -> Image.Image:
        """Render a single PDF page to a PIL Image.

        Args:
            doc: The loaded PDF document.
            page_number: Zero-indexed page number.
            dpi: Resolution for rendering.
            output_path: Optional path to save the rendered image.

        Returns:
            PIL Image of the rendered page.

        Raises:
            PDFRenderError: If rendering fails.
        """
        if page_number < 0 or page_number >= doc.page_count:
            raise PDFRenderError(
                f"Page {page_number} out of range (0-{doc.page_count - 1})"
            )

        try:
            page = doc.load_page(page_number)
            zoom = dpi / 72.0  # 72 is the default PDF DPI
            matrix = fitz.Matrix(zoom, zoom)
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)

            img = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)

            if output_path:
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                img.save(output_path, "PNG")
                logger.debug(
                    "page_rendered",
                    page=page_number,
                    size=f"{img.width}x{img.height}",
                    path=output_path,
                )

            return img

        except Exception as e:
            raise PDFRenderError(
                f"Failed to render page {page_number}: {e}",
                details={"page": page_number, "dpi": dpi},
            ) from e

    def extract_page_digital_elements(
        self,
        doc: fitz.Document,
        page_number: int,
    ) -> tuple[list[SlideElement], int, int]:
        """Extract native digital text blocks and image bounding boxes from PDF if available.

        Returns:
            Tuple of (elements_list, page_width, page_height).
            Returns empty list if page has no selectable text.
        """
        try:
            from app.models.enums import ElementType
            from app.models.schemas import BBox, SlideElement

            page = doc.load_page(page_number)
            rect = page.rect
            page_w, page_h = int(rect.width), int(rect.height)
            if page_w <= 0 or page_h <= 0:
                return [], page_w, page_h

            blocks = page.get_text("blocks")
            elements: list[SlideElement] = []

            for b in blocks:
                x0, y0, x1, y1, text, block_no, block_type = b
                if block_type == 0:  # Text block
                    clean_text = text.strip()
                    if clean_text:
                        lines = clean_text.split("\n")
                        is_short_header = len(lines) == 1 and len(clean_text) < 50 and not clean_text.endswith((".", ","))
                        el_type = ElementType.HEADING if is_short_header else ElementType.PARAGRAPH
                        font_size = 20 if is_short_header else 14
                        elements.append(
                            SlideElement(
                                element_type=el_type,
                                bbox=BBox(x1=x0, y1=y0, x2=x1, y2=y1),
                                text=clean_text,
                                bold=is_short_header,
                                font_size_pt=font_size,
                            )
                        )
                elif block_type == 1:  # Image block
                    elements.append(
                        SlideElement(
                            element_type=ElementType.IMAGE,
                            bbox=BBox(x1=x0, y1=y0, x2=x1, y2=y1),
                            text=f"image_{block_no}",
                        )
                    )

            logger.info(
                "digital_elements_extracted",
                page=page_number + 1,
                total=len(elements),
                text_count=sum(1 for e in elements if e.element_type != ElementType.IMAGE),
                image_count=sum(1 for e in elements if e.element_type == ElementType.IMAGE),
            )
            return elements, page_w, page_h

        except Exception as e:
            logger.warning("digital_text_extract_failed", page=page_number + 1, error=str(e))
            return [], 0, 0

    def render_all_pages(
        self,
        doc: fitz.Document,
        output_dir: str,
        dpi: int = 200,
    ) -> list[str]:
        """Render all pages to PNG files in the output directory.

        Returns:
            List of file paths to rendered page images.
        """
        output_path = Path(output_dir) / "pages"
        output_path.mkdir(parents=True, exist_ok=True)

        image_paths = []
        for i in range(doc.page_count):
            img_path = str(output_path / f"page_{i + 1:04d}.png")
            self.render_page_to_image(doc, i, dpi=dpi, output_path=img_path)
            image_paths.append(img_path)

        logger.info("all_pages_rendered", count=len(image_paths), dir=str(output_path))
        return image_paths
