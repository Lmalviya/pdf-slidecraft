"""Image utility functions for cropping, resizing, and optimization."""

from io import BytesIO
from pathlib import Path

from PIL import Image

from app.core.logging_config import get_logger

logger = get_logger(__name__)


def resize_for_vlm(image: Image.Image, max_dim: int = 512) -> Image.Image:
    """Resize an image so its longest dimension is within max_dim.

    This reduces visual patch count and speeds up VLM CPU inference by ~4-5x.
    Bounding box coordinates remain perfectly proportional.
    """
    width, height = image.width, image.height
    longest_edge = max(width, height)
    if longest_edge <= max_dim:
        return image

    scale = max_dim / longest_edge
    new_width = max(1, int(width * scale))
    new_height = max(1, int(height * scale))
    resized = image.resize((new_width, new_height), Image.Resampling.BILINEAR)
    logger.debug(
        "image_resized_for_vlm",
        original=f"{width}x{height}",
        resized=f"{new_width}x{new_height}",
    )
    return resized


def crop_region(
    image: Image.Image,
    bbox: tuple[float, float, float, float],
    output_path: str | None = None,
    quality: int = 85,
) -> Image.Image:
    """Crop a rectangular region from an image.

    Args:
        image: Source image.
        bbox: (x1, y1, x2, y2) in pixel coordinates.
        output_path: Optional path to save the cropped image.
        quality: JPEG quality if saving.

    Returns:
        Cropped PIL Image.
    """
    x1, y1, x2, y2 = bbox

    # Clamp to image bounds
    x1 = max(0, min(x1, image.width))
    y1 = max(0, min(y1, image.height))
    x2 = max(0, min(x2, image.width))
    y2 = max(0, min(y2, image.height))

    if x2 <= x1 or y2 <= y1:
        logger.warning("invalid_crop_bbox", bbox=bbox)
        # Return a 1x1 transparent pixel as fallback
        return Image.new("RGB", (1, 1), (255, 255, 255))

    cropped = image.crop((int(x1), int(y1), int(x2), int(y2)))

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        fmt = "JPEG" if output_path.lower().endswith((".jpg", ".jpeg")) else "PNG"
        save_kwargs = {"quality": quality} if fmt == "JPEG" else {}
        cropped.save(output_path, fmt, **save_kwargs)

    return cropped


def image_to_bytes(image: Image.Image, fmt: str = "PNG") -> bytes:
    """Convert a PIL Image to bytes."""
    buffer = BytesIO()
    image.save(buffer, format=fmt)
    return buffer.getvalue()


def image_to_stream(image: Image.Image, fmt: str = "PNG") -> BytesIO:
    """Convert a PIL Image to a BytesIO stream (for python-pptx)."""
    buffer = BytesIO()
    image.save(buffer, format=fmt)
    buffer.seek(0)
    return buffer
