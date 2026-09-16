"""File utility functions for safe naming and directory management."""

import re
import unicodedata
from datetime import datetime
from pathlib import Path

from app.core.logging_config import get_logger

logger = get_logger(__name__)


def sanitize_filename(name: str) -> str:
    """Sanitize a filename by removing/replacing unsafe characters."""
    # Normalize unicode characters
    name = unicodedata.normalize("NFKD", name)
    # Remove extension for processing
    stem = Path(name).stem
    # Replace spaces and special chars with underscores
    stem = re.sub(r"[^\w\-.]", "_", stem)
    # Collapse multiple underscores
    stem = re.sub(r"_+", "_", stem).strip("_")
    # Truncate to reasonable length
    return stem[:100] if stem else "document"


def create_output_dir(base_dir: str, pdf_filename: str) -> Path:
    """Create a timestamped output directory for a conversion job.

    Format: output/{timestamp}_{sanitized_filename}/

    Returns:
        Path to the created directory.
    """
    sanitized = sanitize_filename(pdf_filename)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    dir_name = f"{timestamp}_{sanitized}"
    output_path = Path(base_dir) / dir_name
    output_path.mkdir(parents=True, exist_ok=True)

    logger.info("output_dir_created", path=str(output_path))
    return output_path


def get_pptx_path(output_dir: Path, pdf_filename: str) -> Path:
    """Get the path for the output PPTX file."""
    sanitized = sanitize_filename(pdf_filename)
    return output_dir / f"{sanitized}.pptx"
