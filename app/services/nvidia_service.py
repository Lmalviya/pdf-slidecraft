"""NVIDIA NIM Cloud Vision API Service.

Integrates with NVIDIA API Catalog (NIM) multimodal vision models
(e.g., meta/llama-3.2-11b-vision-instruct) using OpenAI-compatible endpoints.
Includes concurrency/RPM rate limiting, automatic backoff, and robust error handling.
"""

from __future__ import annotations

import asyncio
import base64
from io import BytesIO
import httpx
from PIL import Image

from app.config import settings
from app.core.exceptions import VLMError, VLMTimeoutError
from app.core.logging_config import get_logger
from app.core.rate_limiter import AsyncRateLimiter

logger = get_logger(__name__)

# System prompt optimized for Llama 3.2 Vision / Qwen Vision to output structured HTML with coordinates
NVIDIA_VISION_PROMPT = """You are an expert document and slide layout analyzer.
Analyze the provided slide/document image and convert its layout into clean, structured HTML.

Rules:
1. Identify all text blocks, headings, subheadings, and bullet lists.
2. Group related bullet points into <ul><li>...</li></ul> lists.
3. Identify all distinct non-text illustrations, diagrams, medical images, charts, and photographs.
4. For each non-text image region, output:
   <div class="image" data-bbox="[ymin, xmin, ymax, xmax]"></div>
   where ymin, xmin, ymax, xmax are normalized integer coordinates from 0 to 1000.
5. For text elements, you can optionally include data-bbox="[ymin, xmin, ymax, xmax]".
6. Output ONLY valid HTML inside a ```html ``` code block. Do NOT include conversational text.

Example format:
```html
<html>
<body>
  <h1>SLIDE TITLE</h1>
  <ul>
    <li>Main point 1</li>
    <li>Main point 2</li>
  </ul>
  <div class="image" data-bbox="[200, 550, 800, 950]"></div>
</body>
</html>
```
"""


class NvidiaVisionService:
    """Client for NVIDIA NIM Cloud Vision Models with rate limiting and retry handling."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        rate_limiter: AsyncRateLimiter | None = None,
    ):
        self.api_key = api_key or settings.nvidia_api_key or ""
        self.base_url = (base_url or settings.nvidia_base_url).rstrip("/")
        self.model = model or settings.nvidia_default_model
        self.rate_limiter = rate_limiter or AsyncRateLimiter(
            max_concurrency=settings.nvidia_concurrency_limit,
            max_rpm=settings.nvidia_rpm_limit,
        )

    def _image_to_base64_data_url(self, image: Image.Image, max_dim: int = 1280) -> str:
        """Resize image if needed and convert to JPEG base64 data URL."""
        if image.mode != "RGB":
            image = image.convert("RGB")

        # Resize large images to conserve tokens and speed up inference
        w, h = image.size
        if max(w, h) > max_dim:
            scale = max_dim / max(w, h)
            image = image.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)

        buf = BytesIO()
        image.save(buf, format="JPEG", quality=85, optimize=True)
        b64_str = base64.b64encode(buf.getvalue()).decode("utf-8")
        return f"data:image/jpeg;base64,{b64_str}"

    async def analyze_slide_image(
        self,
        image: Image.Image,
        custom_prompt: str | None = None,
        page_number: int = 0,
    ) -> str:
        """Send slide image to NVIDIA NIM Vision model and return the generated HTML layout.

        Args:
            image: High-res PIL Image of the page.
            custom_prompt: Optional override for prompt.
            page_number: Page index for logging.

        Returns:
            Raw HTML layout string containing text and image bboxes.
        """
        if not self.api_key:
            raise VLMError("NVIDIA API Key is missing. Please provide a valid NVIDIA API Key (nvapi-...).")

        data_url = self._image_to_base64_data_url(image)
        prompt_text = custom_prompt or NVIDIA_VISION_PROMPT

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt_text},
                        {
                            "type": "image_url",
                            "image_url": {"url": data_url},
                        },
                    ],
                }
            ],
            "max_tokens": 2048,
            "temperature": 0.1,
            "top_p": 0.95,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        endpoint = f"{self.base_url}/chat/completions"
        max_retries = settings.vlm_max_retries
        start_time = asyncio.get_event_loop().time()

        for attempt in range(1, max_retries + 1):
            async with self.rate_limiter:
                try:
                    logger.info(
                        "nvidia_request_initiated",
                        endpoint=endpoint,
                        model=self.model,
                        page=page_number + 1,
                        attempt=attempt,
                    )

                    async with httpx.AsyncClient(timeout=settings.vlm_timeout_seconds) as client:
                        response = await client.post(endpoint, json=payload, headers=headers)

                    duration_s = round(asyncio.get_event_loop().time() - start_time, 2)

                    # Handle successful response
                    if response.status_code == 200:
                        data = response.json()
                        content = data["choices"][0]["message"]["content"]
                        logger.info(
                            "nvidia_request_successful",
                            page=page_number + 1,
                            model=self.model,
                            duration_s=duration_s,
                            response_len=len(content),
                        )
                        return content

                    # Handle Rate Limiting (429)
                    if response.status_code == 429:
                        retry_after = 5.0
                        if "Retry-After" in response.headers:
                            try:
                                retry_after = float(response.headers["Retry-After"])
                            except ValueError:
                                pass

                        logger.warning(
                            "nvidia_rate_limited",
                            page=page_number + 1,
                            attempt=attempt,
                            retry_after_s=retry_after,
                        )

                        if attempt < max_retries:
                            await asyncio.sleep(retry_after)
                            continue
                        raise VLMError(f"NVIDIA API rate limit exceeded (HTTP 429). {response.text}")

                    # Handle Auth Errors (401/403)
                    if response.status_code in (401, 403):
                        logger.error(
                            "nvidia_auth_failed",
                            status_code=response.status_code,
                            error=response.text,
                        )
                        raise VLMError(f"NVIDIA API Authentication Failed ({response.status_code}): Invalid or expired API Key.")

                    # Handle 5xx Server Errors
                    if response.status_code >= 500:
                        logger.warning(
                            "nvidia_server_error",
                            status_code=response.status_code,
                            attempt=attempt,
                            response_text=response.text[:200],
                        )
                        if attempt < max_retries:
                            backoff = settings.vlm_retry_base_delay * (2 ** (attempt - 1))
                            await asyncio.sleep(backoff)
                            continue
                        raise VLMError(f"NVIDIA API Server Error ({response.status_code}): {response.text}")

                    # Other unexpected HTTP errors
                    raise VLMError(f"NVIDIA API Error ({response.status_code}): {response.text}")

                except httpx.TimeoutException as e:
                    logger.warning("nvidia_timeout", page=page_number + 1, attempt=attempt, error=str(e))
                    if attempt < max_retries:
                        await asyncio.sleep(2.0)
                        continue
                    raise VLMTimeoutError(f"NVIDIA API request timed out after {settings.vlm_timeout_seconds}s") from e

                except httpx.RequestError as e:
                    logger.warning("nvidia_network_error", page=page_number + 1, attempt=attempt, error=str(e))
                    if attempt < max_retries:
                        await asyncio.sleep(2.0)
                        continue
                    raise VLMError(f"NVIDIA API network connection error: {e}") from e

        raise VLMError("NVIDIA API request failed after all retry attempts.")
