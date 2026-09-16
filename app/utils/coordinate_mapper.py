"""Coordinate mapping between image pixel space and PPT EMU space."""

from pptx.util import Emu, Inches

from app.models.schemas import BBox


# Standard PPT slide dimensions (widescreen 16:9)
DEFAULT_SLIDE_WIDTH = Inches(13.333)  # 13.333 inches = standard widescreen
DEFAULT_SLIDE_HEIGHT = Inches(7.5)


def bbox_to_ppt_coords(
    bbox: BBox,
    image_width: int,
    image_height: int,
    slide_width: int = DEFAULT_SLIDE_WIDTH,
    slide_height: int = DEFAULT_SLIDE_HEIGHT,
) -> tuple[int, int, int, int]:
    """Convert image pixel coordinates to PPT EMU coordinates.

    Args:
        bbox: Bounding box in pixel coordinates.
        image_width: Width of the source image in pixels.
        image_height: Height of the source image in pixels.
        slide_width: PPT slide width in EMU.
        slide_height: PPT slide height in EMU.

    Returns:
        Tuple of (left, top, width, height) in EMU.
    """
    # Scale factors
    x_scale = slide_width / image_width
    y_scale = slide_height / image_height

    left = int(bbox.x1 * x_scale)
    top = int(bbox.y1 * y_scale)
    width = int(bbox.width * x_scale)
    height = int(bbox.height * y_scale)

    # Ensure minimum dimensions (avoid zero-size shapes)
    width = max(width, Emu(1))
    height = max(height, Emu(1))

    return left, top, width, height


def scale_bbox_for_resized_image(
    bbox: BBox,
    original_width: int,
    original_height: int,
    resized_width: int,
    resized_height: int,
) -> BBox:
    """Scale bbox coordinates from a resized image back to original image space.

    If the VLM receives a resized image, its bbox output is relative to the
    resized dimensions. This maps them back to the original for accurate cropping.
    """
    x_scale = original_width / resized_width
    y_scale = original_height / resized_height

    return BBox(
        x1=bbox.x1 * x_scale,
        y1=bbox.y1 * y_scale,
        x2=bbox.x2 * x_scale,
        y2=bbox.y2 * y_scale,
    )
