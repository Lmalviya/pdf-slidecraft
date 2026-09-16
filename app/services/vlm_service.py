"""VLM service — communicates with Ollama to analyze page images via Qwen2.5-VL."""

import base64
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image

from app.config import settings
from app.core.exceptions import (
    OllamaConnectionError,
    OllamaModelNotFoundError,
    VLMInferenceError,
    VLMTimeoutError,
)
from app.core.logging_config import get_logger
from app.utils.image_utils import resize_for_vlm

logger = get_logger(__name__)

# System prompt for QwenVL HTML output
VLM_SYSTEM_PROMPT = """You are an expert document OCR and layout extraction system.
Analyze the provided document page image and output ALL text and image regions as HTML tags with exact bounding box pixel coordinates: data-bbox="[x1, y1, x2, y2]" where coordinates are [left, top, right, bottom].

Rules:
1. Every element MUST include data-bbox="[x1, y1, x2, y2]".
2. Use tags: <h1>, <h2>, <h3> for titles/headings, <p> for paragraphs, <ul><li> for bullet points, <table> for tables.
3. For visual images, logos, or diagrams use: <img data-bbox="[x1, y1, x2, y2]" alt="description" />
4. Extract ALL text word-for-word exactly as it appears. Do not skip any text.
5. Output ONLY raw HTML. Do not wrap in explanations.

Example:
<html><body>
<h1 data-bbox="[30, 20, 480, 60]">Document Title</h1>
<p data-bbox="[30, 70, 480, 110]">Introduction paragraph text goes here.</p>
<ul>
  <li data-bbox="[30, 120, 480, 150]">First bullet point description.</li>
  <li data-bbox="[30, 155, 480, 185]">Second bullet point description.</li>
</ul>
<img data-bbox="[30, 200, 250, 380]" alt="System Diagram" />
</body></html>"""

VLM_USER_PROMPT = "Extract all text headings, paragraphs, bullet lists, and images from this document page with data-bbox coordinates in HTML format."


class VLMService:
    """Handles communication with the Ollama VLM for page analysis."""

    def __init__(self):
        self.base_url = settings.ollama_base_url
        self.model_name = settings.vlm_model_name
        self.timeout = settings.vlm_timeout_seconds

    def _image_to_base64(self, image: Image.Image) -> str:
        """Convert PIL Image to base64 string for Ollama API."""
        buffer = BytesIO()
        if image.mode != "RGB":
            image = image.convert("RGB")
        image.save(buffer, format="JPEG", quality=85)
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    async def check_model_available(self) -> bool:
        """Check if the required VLM model is available in Ollama."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                if resp.status_code == 200:
                    models = resp.json().get("models", [])
                    return any(self.model_name in m.get("name", "") for m in models)
                return False
        except httpx.ConnectError:
            return False

    async def analyze_page(
        self,
        image: Image.Image,
        max_width: int | None = None,
    ) -> str:
        """Send a page image to the VLM and get QwenVL HTML response.

        Args:
            image: PIL Image of the rendered PDF page.
            max_width: Max width to resize image to before sending (for speed).

        Returns:
            Raw HTML string from the VLM.

        Raises:
            OllamaConnectionError: Cannot reach Ollama server.
            VLMTimeoutError: Inference exceeded timeout.
            VLMInferenceError: Model returned an error.
        """
        # Resize for VLM input (save CPU memory and speed)
        vlm_width = max_width or settings.max_image_width
        resized_image = resize_for_vlm(image, vlm_width)
        image_b64 = self._image_to_base64(resized_image)

        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": VLM_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": VLM_USER_PROMPT,
                    "images": [image_b64],
                },
            ],
            "stream": False,
            "options": {
                "num_ctx": 2048,
                "num_thread": 8,  # Multi-threaded CPU inference
                "num_predict": 1024,  # Bounded generation limit
                "temperature": 0.1,  # Low temperature for deterministic layout output
            },
        }

        import time as _time
        start_ts = _time.time()
        logger.info(
            "vlm_request_initiated",
            model=self.model_name,
            endpoint=f"{self.base_url}/api/chat",
            input_image_size=f"{image.width}x{image.height}",
            vlm_input_size=f"{resized_image.width}x{resized_image.height}",
            payload_kb=round(len(image_b64) / 1024, 2),
            timeout_s=self.timeout,
        )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                )
                duration_s = round(_time.time() - start_ts, 2)

                if resp.status_code == 404:
                    logger.error("vlm_model_missing", model=self.model_name, duration_s=duration_s)
                    raise OllamaModelNotFoundError(
                        f"Model '{self.model_name}' not found. "
                        f"Run: ollama pull {self.model_name}"
                    )

                if resp.status_code != 200:
                    logger.error(
                        "vlm_http_error",
                        status_code=resp.status_code,
                        response_preview=resp.text[:300],
                        duration_s=duration_s,
                    )
                    raise VLMInferenceError(
                        f"Ollama returned status {resp.status_code}: {resp.text}"
                    )

                result = resp.json()
                content = result.get("message", {}).get("content", "")

                if not content.strip():
                    logger.warning("vlm_empty_content", duration_s=duration_s)
                    raise VLMInferenceError("VLM returned empty response")

                clean_preview = content[:200].replace("\n", " ")
                logger.info(
                    "vlm_request_successful",
                    model=self.model_name,
                    duration_s=duration_s,
                    response_length_chars=len(content),
                    html_preview=clean_preview,
                )
                return content

        except httpx.ConnectError as e:
            logger.error("vlm_connection_refused", endpoint=self.base_url, error=str(e))
            raise OllamaConnectionError(
                f"Cannot connect to Ollama at {self.base_url}: {e}"
            ) from e
        except httpx.TimeoutException as e:
            duration_s = round(_time.time() - start_ts, 2)
            logger.error("vlm_timeout", timeout_limit_s=self.timeout, elapsed_s=duration_s)
            raise VLMTimeoutError(
                f"VLM inference timed out after {self.timeout}s"
            ) from e
        except (OllamaConnectionError, OllamaModelNotFoundError, VLMTimeoutError, VLMInferenceError):
            raise
        except Exception as e:
            logger.error("vlm_unexpected_failure", error=str(e), exc_info=True)
            raise VLMInferenceError(f"Unexpected VLM error: {e}") from e

    def get_resized_dimensions(
        self, image: Image.Image, max_width: int | None = None
    ) -> tuple[int, int]:
        """Get the dimensions the VLM will actually see (after resizing)."""
        vlm_width = max_width or settings.max_image_width
        resized = resize_for_vlm(image, vlm_width)
        return resized.width, resized.height
