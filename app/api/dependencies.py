"""FastAPI dependencies — shared service instances and dependency injection."""

from functools import lru_cache

from app.agents.graph import ConversionPipeline
from app.services.storage_service import StorageService


@lru_cache()
def get_storage_service() -> StorageService:
    """Singleton StorageService instance."""
    return StorageService()


def get_pipeline() -> ConversionPipeline:
    """Create a new ConversionPipeline instance per request."""
    return ConversionPipeline()
