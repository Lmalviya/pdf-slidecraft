"""PPT service — builds editable PowerPoint slides from parsed elements."""

import re
from io import BytesIO
from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

from app.core.exceptions import PPTError, PPTSlideError
from app.core.logging_config import get_logger
from app.models.enums import ElementType
from app.models.schemas import BBox, SlideElement
from app.utils.coordinate_mapper import bbox_to_ppt_coords
from app.utils.image_utils import image_to_stream

logger = get_logger(__name__)

# Alignment mapping
ALIGNMENT_MAP = {
    "left": PP_ALIGN.LEFT,
    "center": PP_ALIGN.CENTER,
    "right": PP_ALIGN.RIGHT,
}


class PPTService:
    """Builds PowerPoint presentations from parsed page elements."""

    def __init__(self):
        self.prs: Presentation | None = None

    def create_presentation(self) -> Presentation:
        """Create a new blank presentation with widescreen dimensions."""
        self.prs = Presentation()
        self.prs.slide_width = Inches(13.333)
        self.prs.slide_height = Inches(7.5)
        logger.info("presentation_created")
        return self.prs

    def get_or_create_presentation(self) -> Presentation:
        """Get existing or create new presentation."""
        if self.prs is None:
            return self.create_presentation()
        return self.prs

    def add_slide_from_elements(
        self,
        elements: list[SlideElement],
        page_image: Image.Image,
        page_number: int,
        image_width: int,
        image_height: int,
    ) -> None:
        """Add a slide to the presentation from parsed elements.

        Args:
            elements: List of SlideElements (text boxes and image regions).
            page_image: Original full-resolution page image (for cropping).
            page_number: Page number (for logging).
            image_width: Width of the image the VLM analyzed (may be resized).
            image_height: Height of the image the VLM analyzed.
        """
        prs = self.get_or_create_presentation()

        try:
            # Use blank layout (index 6)
            slide_layout = prs.slide_layouts[6]
            slide = prs.slides.add_slide(slide_layout)

            text_count = 0
            image_count = 0

            for element in elements:
                try:
                    if element.element_type == ElementType.FULL_PAGE_IMAGE:
                        # Fallback: entire page as a single image
                        self._add_full_page_image(slide, page_image, prs)
                        image_count += 1
                    elif element.element_type == ElementType.IMAGE:
                        self._add_image_element(
                            slide, element, page_image, image_width, image_height, prs
                        )
                        image_count += 1
                    else:
                        self._add_text_element(
                            slide, element, image_width, image_height, prs
                        )
                        text_count += 1
                except Exception as e:
                    logger.warning(
                        "element_add_failed",
                        page=page_number,
                        element_type=element.element_type,
                        error=str(e),
                    )
                    continue

            logger.info(
                "slide_added",
                page=page_number,
                text_elements=text_count,
                image_elements=image_count,
            )

        except Exception as e:
            raise PPTSlideError(
                f"Failed to build slide for page {page_number}: {e}",
                details={"page": page_number},
            ) from e

    def add_full_page_image_slide(
        self, page_image: Image.Image, page_number: int
    ) -> None:
        """Add a slide with the entire page as a full-page image (fallback)."""
        prs = self.get_or_create_presentation()
        slide_layout = prs.slide_layouts[6]
        slide = prs.slides.add_slide(slide_layout)
        self._add_full_page_image(slide, page_image, prs)
        logger.info("full_page_image_slide_added", page=page_number)

    def _add_text_element(self, slide, element: SlideElement, img_w, img_h, prs):
        """Add an editable formatted text box to the slide with multi-paragraph support."""
        left, top, width, height = bbox_to_ppt_coords(
            element.bbox, img_w, img_h, prs.slide_width, prs.slide_height
        )

        # Add generous width margin to prevent premature line wrapping
        adjusted_width = min(prs.slide_width - left, int(width * 1.05))
        txBox = slide.shapes.add_textbox(left, top, adjusted_width, height)
        tf = txBox.text_frame
        tf.word_wrap = True
        tf.margin_left = Inches(0.05)
        tf.margin_right = Inches(0.05)
        tf.margin_top = Inches(0.05)
        tf.margin_bottom = Inches(0.05)

        raw_text = element.text or ""
        lines = [line.strip() for line in raw_text.split("\n") if line.strip()]
        if not lines:
            return

        align = ALIGNMENT_MAP.get(element.alignment, PP_ALIGN.LEFT)

        for i, line_text in enumerate(lines):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.alignment = align

            # Detect sub-bullet items (e.g. a), b), c), -)
            is_sub_bullet = bool(re.match(r"^([a-zA-Z][\.\)]|\([a-zA-Z0-9]+\))\s*", line_text))

            # Format bullet prefixes
            if element.element_type == ElementType.BULLET:
                if is_sub_bullet:
                    p.level = 1
                elif not re.match(r"^([•\-\*■◆○●►–—]|\d+[\.\)])\s*", line_text):
                    line_text = f"• {line_text}"

            run = p.add_run()
            run.text = line_text

            font = run.font
            font.size = Pt(element.font_size_pt)
            font.bold = element.bold
            font.italic = element.italic

            # Professional color palette
            if element.element_type == ElementType.HEADING:
                font.color.rgb = RGBColor(0x0A, 0x4D, 0x68)  # Deep professional teal/navy
                font.bold = True
                font.size = Pt(max(24, element.font_size_pt))
            elif element.element_type == ElementType.SUBHEADING:
                font.color.rgb = RGBColor(0x1A, 0x36, 0x5D)
                font.bold = True
            else:
                font.color.rgb = RGBColor(0x22, 0x22, 0x22)  # High-contrast charcoal text

    def _add_image_element(self, slide, element: SlideElement, page_image, img_w, img_h, prs):
        """Crop the image region from the page and add it to the slide."""
        # Scale bbox from VLM image space to original image space
        scale_x = page_image.width / img_w
        scale_y = page_image.height / img_h

        crop_box = (
            int(element.bbox.x1 * scale_x),
            int(element.bbox.y1 * scale_y),
            int(element.bbox.x2 * scale_x),
            int(element.bbox.y2 * scale_y),
        )

        # Clamp to image bounds
        crop_box = (
            max(0, min(crop_box[0], page_image.width)),
            max(0, min(crop_box[1], page_image.height)),
            max(0, min(crop_box[2], page_image.width)),
            max(0, min(crop_box[3], page_image.height)),
        )

        if crop_box[2] <= crop_box[0] or crop_box[3] <= crop_box[1]:
            logger.warning("skipping_invalid_image_crop", bbox=element.bbox)
            return

        cropped = page_image.crop(crop_box)
        img_stream = image_to_stream(cropped, fmt="PNG")

        # Map position to slide coordinates
        left, top, width, height = bbox_to_ppt_coords(
            element.bbox, img_w, img_h, prs.slide_width, prs.slide_height
        )

        slide.shapes.add_picture(img_stream, left, top, width, height)

    def _add_full_page_image(self, slide, page_image: Image.Image, prs):
        """Add the full page image filling the entire slide."""
        img_stream = image_to_stream(page_image, fmt="PNG")
        slide.shapes.add_picture(
            img_stream, Emu(0), Emu(0), prs.slide_width, prs.slide_height
        )

    def save(self, output_path: str) -> str:
        """Save the presentation to disk.

        Returns:
            The path where the file was saved.
        """
        if self.prs is None:
            raise PPTError("No presentation to save")

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.prs.save(str(path))
        logger.info("presentation_saved", path=str(path))
        return str(path)

    def save_intermediate(self, output_path: str) -> str:
        """Save an intermediate copy (for partial downloads)."""
        return self.save(output_path)
