"""Modern, interactive Gradio UI for PDF-SlideCraft with multi-provider engine selection."""

from __future__ import annotations

import asyncio
from pathlib import Path

import gradio as gr

from app.agents.callbacks import PageUpdate, ProgressTracker
from app.agents.graph import ConversionPipeline
from app.api.routes.convert import register_job
from app.config import settings
from app.core.logging_config import get_logger
from app.models.enums import PageStatus, ProcessingEngine

logger = get_logger(__name__)

ENGINE_CHOICE_MAP = {
    "⚡ Local Fast Layout + OCR (Offline CPU, ~1-2s/page)": ProcessingEngine.LOCAL_OCR,
    "☁️ NVIDIA NIM Vision Cloud API (Free Models, High Accuracy)": ProcessingEngine.NVIDIA_API,
    "🦙 Local Ollama VLM (Offline Qwen2.5-VL)": ProcessingEngine.LOCAL_VLM,
}

REVERSE_ENGINE_MAP = {v: k for k, v in ENGINE_CHOICE_MAP.items()}


def create_gradio_ui() -> gr.Blocks:
    """Create and return the Gradio Blocks UI."""

    custom_css = """
    .main-title {
        font-family: 'Inter', system-ui, sans-serif;
        font-weight: 800;
        background: linear-gradient(135deg, #2563eb 0%, #7c3aed 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.25rem;
    }
    .engine-card {
        border-radius: 10px;
        padding: 12px;
        background: rgba(37, 99, 235, 0.04);
        border: 1px solid rgba(37, 99, 235, 0.15);
    }
    .stat-badge {
        display: inline-block;
        padding: 4px 10px;
        border-radius: 6px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    """

    with gr.Blocks(
        title="PDF-SlideCraft — PDF to Editable PowerPoint",
    ) as demo:
        # Header
        gr.Markdown(
            """
            # 🎨 PDF-SlideCraft
            ### Convert PDF slide scans, lecture notes, and documents into fully editable PowerPoint (.pptx) presentations in seconds.
            """,
        )

        with gr.Row():
            # Left column: Upload + Engine Selection + Settings
            with gr.Column(scale=2):
                pdf_input = gr.File(
                    label="📁 Upload PDF File",
                    file_types=[".pdf"],
                    type="binary",
                )

                engine_selector = gr.Radio(
                    choices=list(ENGINE_CHOICE_MAP.keys()),
                    value=REVERSE_ENGINE_MAP[ProcessingEngine.LOCAL_OCR],
                    label="⚡ Select Processing Engine",
                    info="Choose between ultra-fast local CPU OCR, cloud NVIDIA NIM Vision, or local Ollama VLM",
                )

                # Dynamic Provider Settings
                with gr.Group(visible=False) as nvidia_box:
                    gr.Markdown("#### ☁️ NVIDIA NIM Cloud Vision Configuration")
                    nvidia_key_input = gr.Textbox(
                        label="NVIDIA API Key",
                        placeholder="nvapi-xxxxxxxxxxxxxxxxxxxxxxxxxxxx",
                        value=settings.nvidia_api_key or "",
                        type="password",
                        info="Get your free API key at build.nvidia.com",
                    )
                    nvidia_model_dropdown = gr.Dropdown(
                        choices=[
                            ("Llama 3.2 11B Vision (Recommended - Fast & Sharp)", "meta/llama-3.2-11b-vision-instruct"),
                            ("Llama 3.2 90B Vision (High Accuracy for Complex Decks)", "meta/llama-3.2-90b-vision-instruct"),
                        ],
                        value="meta/llama-3.2-11b-vision-instruct",
                        label="NVIDIA Vision Model",
                    )

                with gr.Group(visible=False) as ollama_box:
                    gr.Markdown("#### 🦙 Local Ollama Configuration")
                    ollama_model_input = gr.Textbox(
                        label="Ollama Model Name",
                        value=settings.vlm_model_name,
                        info="Model must be pulled locally in Ollama",
                    )

                with gr.Group(visible=True) as local_ocr_box:
                    gr.Markdown(
                        "ℹ️ **Local Engine:** Runs 100% on CPU using RapidOCR + OpenCV layout engine. Zero setup, 0 cost, ~1-2s per page."
                    )

                with gr.Accordion("⚙️ Advanced Settings", open=False):
                    workers_slider = gr.Slider(
                        minimum=1,
                        maximum=4,
                        value=2,
                        step=1,
                        label="Parallel Page Workers",
                        info="Number of concurrent pages to process",
                    )
                    dpi_dropdown = gr.Dropdown(
                        choices=[100, 150, 200, 300],
                        value=150,
                        label="Render DPI",
                        info="150 DPI is recommended for optimal speed and visual clarity",
                    )
                    quality_slider = gr.Slider(
                        minimum=50,
                        maximum=100,
                        value=85,
                        step=5,
                        label="Image Quality (%)",
                        info="Quality of cropped photo/diagram exports",
                    )

                convert_btn = gr.Button(
                    "🚀 Convert to PPTX",
                    variant="primary",
                    size="lg",
                    interactive=True,
                )

            # Right column: Live Status, Metrics & Console
            with gr.Column(scale=3):
                gr.Markdown("### 📊 Conversion Progress & Live Console")
                progress_text = gr.Textbox(
                    label="Current Status",
                    value="Ready — upload a PDF to begin conversion",
                    interactive=False,
                    lines=1,
                )
                progress_bar = gr.Slider(
                    minimum=0,
                    maximum=100,
                    value=0,
                    label="Completion Progress (%)",
                    interactive=False,
                )

                processing_log = gr.Textbox(
                    label="📋 Real-Time Structured Activity Log",
                    value="",
                    interactive=False,
                    lines=12,
                    max_lines=25,
                    autoscroll=True,
                )

                # Download card
                with gr.Group(visible=False) as result_card:
                    gr.Markdown("### 🎉 Presentation Ready!")
                    download_file = gr.File(
                        label="⬇️ Download Editable PowerPoint (.pptx)",
                        interactive=False,
                    )

        # --- Dynamic Engine Toggle Logic ---
        def on_engine_change(selected_label: str):
            selected_engine = ENGINE_CHOICE_MAP.get(selected_label, ProcessingEngine.LOCAL_OCR)
            return (
                gr.update(visible=selected_engine == ProcessingEngine.NVIDIA_API),
                gr.update(visible=selected_engine == ProcessingEngine.LOCAL_VLM),
                gr.update(visible=selected_engine == ProcessingEngine.LOCAL_OCR),
            )

        engine_selector.change(
            fn=on_engine_change,
            inputs=[engine_selector],
            outputs=[nvidia_box, ollama_box, local_ocr_box],
        )

        # --- Conversion Task Execution ---
        async def convert_pdf(
            pdf_file,
            selected_engine_label,
            nvidia_key,
            nvidia_model,
            ollama_model,
            workers,
            dpi,
            quality,
            progress=gr.Progress(),
        ):
            """Execute end-to-end conversion with real-time UI log streaming."""
            if pdf_file is None:
                gr.Warning("Please upload a PDF file first.")
                yield (
                    "❌ No PDF uploaded",
                    0,
                    "Please upload a PDF file to begin.",
                    gr.update(visible=False),
                    gr.update(visible=False, value=None),
                )
                return

            selected_engine = ENGINE_CHOICE_MAP.get(selected_engine_label, ProcessingEngine.LOCAL_OCR)
            filename = "document.pdf"
            pipeline = ConversionPipeline()
            tracker = ProgressTracker(job_id="active", total_pages=0)

            update_queue: asyncio.Queue[PageUpdate] = asyncio.Queue()
            loop = asyncio.get_running_loop()

            def on_page_update(update: PageUpdate):
                loop.call_soon_threadsafe(update_queue.put_nowait, update)

            tracker.register_callback(on_page_update)

            engine_names = {
                ProcessingEngine.LOCAL_OCR: "Local RapidOCR + OpenCV",
                ProcessingEngine.NVIDIA_API: f"NVIDIA NIM ({nvidia_model})",
                ProcessingEngine.LOCAL_VLM: f"Ollama ({ollama_model})",
            }

            log_entries: list[str] = [
                f"🚀 Initializing PDF-SlideCraft pipeline...",
                f"⚙️ Selected Engine: {engine_names.get(selected_engine)}",
                f"📄 DPI: {dpi} | Parallel Workers: {workers}",
            ]

            yield (
                "🔄 Initializing conversion...",
                0,
                "\n".join(log_entries),
                gr.update(visible=False),
                gr.update(visible=False, value=None),
            )

            # Start pipeline task in background
            pipeline_task = asyncio.create_task(
                pipeline.run(
                    pdf_content=pdf_file,
                    pdf_filename=filename,
                    engine=selected_engine,
                    nvidia_api_key=nvidia_key.strip() if nvidia_key else None,
                    nvidia_model=nvidia_model,
                    ollama_model=ollama_model,
                    parallel_workers=int(workers),
                    dpi=int(dpi),
                    image_quality=int(quality),
                    progress_tracker=tracker,
                )
            )

            icon_map = {
                PageStatus.PENDING: "⏳",
                PageStatus.RENDERING: "🖼️",
                PageStatus.ANALYZING: "🧠",
                PageStatus.PARSING: "🔍",
                PageStatus.BUILDING: "📐",
                PageStatus.COMPLETED: "✅",
                PageStatus.FALLBACK: "⚠️",
                PageStatus.FAILED: "❌",
            }

            while not pipeline_task.done():
                try:
                    update: PageUpdate = await asyncio.wait_for(update_queue.get(), timeout=0.3)
                    icon = icon_map.get(update.status, "ℹ️")
                    time_str = f" ({update.processing_time:.1f}s)" if update.processing_time > 0 else ""
                    log_line = f"{icon} Page {update.page_number + 1:2d}: {update.message}{time_str}"
                    log_entries.append(log_line)

                    status_str = f"Processing: {tracker.progress_text}"
                    pct = tracker.progress_percent

                    yield (
                        status_str,
                        pct,
                        "\n".join(log_entries[-35:]),
                        gr.update(visible=False),
                        gr.update(visible=False, value=None),
                    )
                except asyncio.TimeoutError:
                    if tracker.total_pages > 0:
                        status_str = f"Processing: {tracker.progress_text}"
                        pct = tracker.progress_percent
                        yield (
                            status_str,
                            pct,
                            "\n".join(log_entries[-35:]),
                            gr.update(visible=False),
                            gr.update(visible=False, value=None),
                        )

            # Drain queue
            while not update_queue.empty():
                update = update_queue.get_nowait()
                icon = icon_map.get(update.status, "ℹ️")
                time_str = f" ({update.processing_time:.1f}s)" if update.processing_time > 0 else ""
                log_entries.append(f"{icon} Page {update.page_number + 1:2d}: {update.message}{time_str}")

            job = await pipeline_task
            register_job(job)

            pptx_path = job.pptx_path
            pptx_exists = Path(pptx_path).exists() if pptx_path else False

            log_entries.append("=" * 45)
            if job.status == "completed" and pptx_exists:
                total_text = sum(p.text_elements_count for p in job.page_results)
                total_imgs = sum(p.image_elements_count for p in job.page_results)
                log_entries.append(
                    f"🎉 Conversion finished! {job.processed_pages} slides created ({total_text} text boxes, {total_imgs} images/diagrams)."
                )
                status_text = f"✅ Conversion Complete ({job.processed_pages}/{job.total_pages} slides)"
                yield (
                    status_text,
                    100,
                    "\n".join(log_entries),
                    gr.update(visible=True),
                    gr.update(visible=True, value=pptx_path),
                )
            elif pptx_exists:
                log_entries.append(f"⚠️ Completed with partial fallbacks ({job.processed_pages}/{job.total_pages} slides).")
                status_text = f"⚠️ Completed with fallbacks ({job.processed_pages}/{job.total_pages} slides)"
                yield (
                    status_text,
                    100,
                    "\n".join(log_entries),
                    gr.update(visible=True),
                    gr.update(visible=True, value=pptx_path),
                )
            else:
                log_entries.append("❌ Conversion failed. Review errors above.")
                status_text = "❌ Conversion failed."
                yield (
                    status_text,
                    0,
                    "\n".join(log_entries),
                    gr.update(visible=False),
                    gr.update(visible=False, value=None),
                )

        # Wire up event handler
        convert_btn.click(
            fn=convert_pdf,
            inputs=[
                pdf_input,
                engine_selector,
                nvidia_key_input,
                nvidia_model_dropdown,
                ollama_model_input,
                workers_slider,
                dpi_dropdown,
                quality_slider,
            ],
            outputs=[
                progress_text,
                progress_bar,
                processing_log,
                result_card,
                download_file,
            ],
        )

    return demo
