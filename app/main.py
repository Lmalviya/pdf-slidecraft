"""FastAPI application entry point — mounts Gradio UI and API routes."""

from contextlib import asynccontextmanager

import gradio as gr
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.convert import router as convert_router
from app.api.routes.health import router as health_router
from app.config import settings
from app.core.logging_config import get_logger, setup_logging
from frontend.gradio_ui import create_gradio_ui

# Initialize logging
setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    logger.info(
        "app_starting",
        host=settings.app_host,
        port=settings.app_port,
        model=settings.vlm_model_name,
        ollama_url=settings.ollama_base_url,
    )
    yield
    logger.info("app_shutting_down")


# Create FastAPI app
app = FastAPI(
    title="PDF to Editable PPT Converter",
    description="Convert PDF pages to editable PowerPoint slides using AI",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS (allow Gradio frontend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routes
app.include_router(health_router)
app.include_router(convert_router)

# Create and mount Gradio UI
gradio_app = create_gradio_ui()
app = gr.mount_gradio_app(app, gradio_app, path="/")

logger.info("app_configured", routes=["/", "/health", "/api/v1"])
