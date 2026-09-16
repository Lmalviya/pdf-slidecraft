"""Progress callback system for real-time UI updates."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Callable

from app.core.logging_config import get_logger
from app.models.enums import PageStatus

logger = get_logger(__name__)


@dataclass
class PageUpdate:
    """A progress update for a single page."""
    page_number: int
    status: PageStatus
    message: str
    processing_time: float = 0.0
    text_count: int = 0
    image_count: int = 0


@dataclass
class ProgressTracker:
    """Tracks and broadcasts progress updates for a conversion job.

    The Gradio UI polls this tracker for progress updates.
    """
    job_id: str
    total_pages: int
    processed_pages: int = 0
    page_updates: list[PageUpdate] = field(default_factory=list)
    _callbacks: list[Callable] = field(default_factory=list)
    _avg_time_per_page: float = 0.0

    def register_callback(self, callback: Callable) -> None:
        """Register a callback to be called on each update."""
        self._callbacks.append(callback)

    def update_page(self, update: PageUpdate) -> None:
        """Record a page processing update."""
        self.page_updates.append(update)

        if update.status in (PageStatus.COMPLETED, PageStatus.FALLBACK):
            self.processed_pages += 1
            # Update running average
            if update.processing_time > 0:
                total_time = sum(
                    u.processing_time
                    for u in self.page_updates
                    if u.status in (PageStatus.COMPLETED, PageStatus.FALLBACK)
                    and u.processing_time > 0
                )
                self._avg_time_per_page = total_time / self.processed_pages

        # Notify callbacks
        for cb in self._callbacks:
            try:
                cb(update)
            except Exception as e:
                logger.warning("progress_callback_error", error=str(e))

    @property
    def progress_fraction(self) -> float:
        """Progress as a fraction (0.0 to 1.0)."""
        if self.total_pages == 0:
            return 0.0
        return self.processed_pages / self.total_pages

    @property
    def progress_percent(self) -> int:
        """Progress as an integer percentage."""
        return int(self.progress_fraction * 100)

    @property
    def estimated_remaining_seconds(self) -> float | None:
        """Estimated seconds remaining based on average page time."""
        remaining_pages = self.total_pages - self.processed_pages
        if self._avg_time_per_page > 0 and remaining_pages > 0:
            return self._avg_time_per_page * remaining_pages
        return None

    @property
    def progress_text(self) -> str:
        """Human-readable progress string."""
        est = self.estimated_remaining_seconds
        if est and est > 60:
            est_str = f" (est. ~{est / 60:.0f} min remaining)"
        elif est:
            est_str = f" (est. ~{est:.0f}s remaining)"
        else:
            est_str = ""

        return (
            f"{self.processed_pages} / {self.total_pages} pages "
            f"({self.progress_percent}%){est_str}"
        )

    @property
    def log_text(self) -> str:
        """Full processing log as multiline text."""
        lines = []
        for u in self.page_updates:
            icon = {
                PageStatus.COMPLETED: "✅",
                PageStatus.FALLBACK: "⚠️",
                PageStatus.FAILED: "❌",
                PageStatus.ANALYZING: "🔄",
                PageStatus.RENDERING: "📄",
            }.get(u.status, "⏳")

            time_str = f" ({u.processing_time:.1f}s)" if u.processing_time > 0 else ""
            lines.append(f"{icon} Page {u.page_number + 1:3d} - {u.message}{time_str}")

        return "\n".join(lines)
