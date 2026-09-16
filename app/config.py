"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Central configuration for the PDF-to-PPT converter."""

    # Processing Engine
    default_engine: str = Field(default="local_ocr", description="Default engine: local_ocr, nvidia_api, local_vlm")

    # NVIDIA NIM Cloud Vision API
    nvidia_api_key: str | None = Field(default=None, description="NVIDIA NIM API key (nvapi-...)")
    nvidia_base_url: str = Field(default="https://integrate.api.nvidia.com/v1", description="NVIDIA API base URL")
    nvidia_default_model: str = Field(default="meta/llama-3.2-11b-vision-instruct", description="NVIDIA Vision Model")
    nvidia_rpm_limit: int = Field(default=30, ge=1, le=120, description="Max requests per minute for NVIDIA API")
    nvidia_concurrency_limit: int = Field(default=2, ge=1, le=8, description="Max concurrent NVIDIA requests")

    # Ollama
    ollama_base_url: str = Field(default="http://ollama:11434", description="Ollama server URL")
    vlm_model_name: str = Field(default="qwen2.5vl:3b", description="Vision-language model name")

    # Processing
    max_parallel_workers: int = Field(default=2, ge=1, le=10, description="Concurrent page workers")
    default_dpi: int = Field(default=150, ge=100, le=400, description="PDF render DPI")
    default_image_quality: int = Field(default=85, ge=50, le=100, description="JPEG quality %")
    max_image_width: int = Field(default=1024, ge=256, le=2048, description="Max image dimension for VLM")

    # VLM Reliability
    vlm_timeout_seconds: int = Field(default=120, description="VLM call timeout")
    vlm_max_retries: int = Field(default=3, ge=1, le=10, description="Max retry attempts")
    vlm_retry_base_delay: float = Field(default=1.0, description="Retry base delay in seconds")
    circuit_breaker_failure_threshold: int = Field(default=5, description="Failures before circuit opens")
    circuit_breaker_recovery_timeout: int = Field(default=60, description="Seconds before half-open")

    # Application
    app_host: str = Field(default="0.0.0.0")
    app_port: int = Field(default=7860)
    log_level: str = Field(default="INFO")
    output_dir: str = Field(default="./output")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


# Singleton instance
settings = Settings()
