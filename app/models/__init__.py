"""Enumerations for type safety across the application."""

from enum import Enum


class ElementType(str, Enum):
    """Type of content element detected on a page."""
    HEADING = "heading"
    SUBHEADING = "subheading"
    PARAGRAPH = "paragraph"
    BULLET = "bullet"
    IMAGE = "image"
    TABLE = "table"
    CAPTION = "caption"
    FULL_PAGE_IMAGE = "full_page_image"


class JobStatus(str, Enum):
    """Status of a conversion job."""
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PageStatus(str, Enum):
    """Processing status of a single page."""
    PENDING = "pending"
    RENDERING = "rendering"
    ANALYZING = "analyzing"
    PARSING = "parsing"
    BUILDING = "building"
    COMPLETED = "completed"
    FAILED = "failed"
    FALLBACK = "fallback"
