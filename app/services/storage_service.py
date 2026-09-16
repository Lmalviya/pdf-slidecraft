"""Storage service — manages output directories and file lifecycle."""

import shutil
from pathlib import Path

from app.config import settings
from app.core.exceptions import StorageError
from app.core.logging_config import get_logger
from app.utils.file_utils import create_output_dir, get_pptx_path

logger = get_logger(__name__)


class StorageService:
    """Manages file storage, output directories, and cleanup."""

    def __init__(self, base_output_dir: str | None = None):
        self.base_output_dir = Path(base_output_dir or settings.output_dir)
        self.base_output_dir.mkdir(parents=True, exist_ok=True)

    def create_job_directory(self, pdf_filename: str) -> tuple[Path, Path]:
        """Create a timestamped output directory for a job.

        Returns:
            Tuple of (output_dir, pptx_path).
        """
        try:
            output_dir = create_output_dir(str(self.base_output_dir), pdf_filename)
            pptx_path = get_pptx_path(output_dir, pdf_filename)
            pages_dir = output_dir / "pages"
            pages_dir.mkdir(exist_ok=True)
            return output_dir, pptx_path
        except Exception as e:
            raise StorageError(f"Failed to create job directory: {e}") from e

    def save_uploaded_pdf(self, pdf_content: bytes, output_dir: Path, filename: str) -> Path:
        """Save uploaded PDF to the job directory.

        Returns:
            Path to the saved PDF.
        """
        try:
            pdf_path = output_dir / filename
            pdf_path.write_bytes(pdf_content)
            logger.info("pdf_saved", path=str(pdf_path), size_mb=len(pdf_content) / 1024 / 1024)
            return pdf_path
        except Exception as e:
            raise StorageError(f"Failed to save uploaded PDF: {e}") from e

    def get_page_image_path(self, output_dir: Path, page_number: int) -> Path:
        """Get the path for a page image file."""
        return output_dir / "pages" / f"page_{page_number + 1:04d}.png"

    def get_cropped_image_path(
        self, output_dir: Path, page_number: int, element_index: int
    ) -> Path:
        """Get the path for a cropped image element."""
        crops_dir = output_dir / "pages" / "crops"
        crops_dir.mkdir(exist_ok=True)
        return crops_dir / f"page_{page_number + 1:04d}_img_{element_index:03d}.png"

    def file_exists(self, path: Path) -> bool:
        """Check if a file exists."""
        return path.exists() and path.is_file()

    def get_file_size(self, path: Path) -> int:
        """Get file size in bytes."""
        return path.stat().st_size if path.exists() else 0

    def cleanup_job(self, output_dir: Path) -> None:
        """Remove a job's output directory (for failed/cancelled jobs)."""
        try:
            if output_dir.exists():
                shutil.rmtree(output_dir)
                logger.info("job_directory_cleaned", path=str(output_dir))
        except Exception as e:
            logger.error("cleanup_failed", path=str(output_dir), error=str(e))
