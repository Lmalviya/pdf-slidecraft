"""Custom exception hierarchy for structured error handling."""


class AppError(Exception):
    """Base exception for all application errors."""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


# --- PDF Errors ---

class PDFError(AppError):
    """Base for PDF-related errors."""


class PDFLoadError(PDFError):
    """Failed to load or parse the PDF file."""


class PDFRenderError(PDFError):
    """Failed to render a PDF page to image."""


# --- VLM / Ollama Errors ---

class VLMError(AppError):
    """Base for VLM/Ollama service errors."""


class OllamaConnectionError(VLMError):
    """Cannot connect to the Ollama server."""


class OllamaModelNotFoundError(VLMError):
    """The requested model is not available in Ollama."""


class VLMTimeoutError(VLMError):
    """VLM inference exceeded the timeout limit."""


class VLMInferenceError(VLMError):
    """VLM returned an error or unparseable response."""


class MaxRetriesExceededError(VLMError):
    """All retry attempts have been exhausted."""


class CircuitBreakerOpenError(VLMError):
    """Circuit breaker is open — Ollama service is considered unavailable."""


# --- HTML Parsing Errors ---

class HTMLParsingError(AppError):
    """Failed to parse the QwenVL HTML response."""


# --- PPT Errors ---

class PPTError(AppError):
    """Base for PPT generation errors."""


class PPTSlideError(PPTError):
    """Failed to build a specific slide."""


# --- Storage Errors ---

class StorageError(AppError):
    """File system / storage related error."""
