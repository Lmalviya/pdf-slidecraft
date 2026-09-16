"""Health check endpoint."""

from fastapi import APIRouter
import httpx

from app.config import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict:
    """Check application health including Ollama connectivity and model availability."""
    status = {"app": "ok", "ollama": "unknown", "model": "unknown"}

    # Check Ollama server
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{settings.ollama_base_url}/")
            status["ollama"] = "ok" if resp.status_code == 200 else "error"
    except Exception as e:
        status["ollama"] = f"error: {e}"
        logger.warning("ollama_health_check_failed", error=str(e))

    # Check if model is available
    if status["ollama"] == "ok":
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{settings.ollama_base_url}/api/tags")
                if resp.status_code == 200:
                    models = resp.json().get("models", [])
                    model_names = [m.get("name", "") for m in models]
                    if any(settings.vlm_model_name in name for name in model_names):
                        status["model"] = "ok"
                    else:
                        status["model"] = f"not_found (available: {model_names})"
        except Exception as e:
            status["model"] = f"error: {e}"

    overall = "healthy" if all(v == "ok" for v in status.values()) else "degraded"
    return {"status": overall, "components": status}
