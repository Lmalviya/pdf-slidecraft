"""Unit tests for NvidiaVisionService."""

import asyncio
from PIL import Image

from app.core.exceptions import VLMError
from app.services.nvidia_service import NvidiaVisionService


def test_nvidia_service_missing_api_key():
    """Verify error raised when API key is missing."""
    service = NvidiaVisionService(api_key="")
    img = Image.new("RGB", (100, 100), color="white")

    raised = False
    try:
        asyncio.run(service.analyze_slide_image(img))
    except VLMError:
        raised = True

    assert raised, "Expected VLMError when API key is missing"


def test_nvidia_image_base64_conversion():
    """Verify image to base64 data url formatting."""
    service = NvidiaVisionService(api_key="nvapi-test12345")
    img = Image.new("RGB", (200, 200), color="blue")
    data_url = service._image_to_base64_data_url(img)

    assert data_url.startswith("data:image/jpeg;base64,")
    assert len(data_url) > 100
