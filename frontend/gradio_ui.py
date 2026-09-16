"""Gradio UI for the PDF-to-PPT converter."""

from __future__ import annotations

import asyncio
from pathlib import Path

import gradio as gr

from app.agents.callbacks import PageUpdate, ProgressTracker
from app.agents.graph import ConversionPipeline
from app.api.routes.convert import register_job
from app.core.logging_config import get_logger
from app.models.enums import PageStatus

logger = get_logger(__name__)


def create_gradio_ui() -> gr.Blocks:
    """Create and return the Gradio Blocks UI."""

    with gr.Blocks(
        title="PDF to Editable PPT Converter",
    ) as demo:
        # Header
        gr.Markdown(
            """
            # 📄 PDF to Editable PPT Converter
            Upload a PDF and get an editable PowerPoint — text extracted as editable text boxes, images/diagrams preserved as pictures.
            """,
        )

        with gr.Row():
            # Left column: Upload + Settings
            with gr.Column(scale=2):
                pdf_input = gr.File(
                    label="📁 Upload PDF",
                    file_types=[".pdf"],
                    type="binary",
                )

                with gr.Accordion("⚙️ Settings", open=False):
                    workers_slider = gr.Slider(
                        minimum=1,
                        maximum=4,
                        value=1,
                        step=1,
                        label="Parallel Workers",
                        info="1 recommended for CPU (Intel i5); 2+ for GPU systems",
                    )
                    dpi_dropdown = gr.Dropdown(
                        choices=[150, 200, 300],
                        value=200,
                        label="Image DPI",
                        info="Higher DPI = better quality but slower",
                    )
                    quality_slider = gr.Slider(
                        minimum=50,
                        maximum=100,
                        value=85,
                        step=5,
                        label="Image Quality (%)",
                        info="Quality of cropped images in PPT",
                    )

                convert_btn = gr.Button(
                    "🚀 Convert to PPT",
                    variant="primary",
                    size="lg",
                    interactive=True,
                )

            # Right column: Status & Live Log
            with gr.Column(scale=3):
                gr.Markdown("### 📊 Progress & Live Status")
                progress_text = gr.Textbox(
                    label="Status",
                    value="Ready — upload a PDF to begin",
                    interactive=False,
                    lines=1,
                )
                progress_bar = gr.Slider(
                    minimum=0,
                    maximum=100,
                    value=0,
                    label="Completion",
                    interactive=False,
                )

                processing_log = gr.Textbox(
                    label="📋 Live Processing Log",
                    value="",
                    interactive=False,
                    lines=12,
                    max_lines=25,
                    autoscroll=True,
                )

        # Download section
        with gr.Row():
            with gr.Column():
                gr.Markdown("### ⬇️ Downloads")
            with gr.Column():
                output_path_text = gr.Textbox(
                    label="Output directory",
                    value="",
                    interactive=False,
                    visible=False,
                )

        with gr.Row():
            partial_download = gr.File(
                label="⬇️ Download Current PPT (partial)",
                visible=False,
                interactive=False,
            )
            final_download = gr.File(
                label="⬇️ Download Final PPT",
                visible=False,
                interactive=False,
            )

        # --- Event Handlers ---

        async def convert_pdf(pdf_file, workers, dpi, quality, progress=gr.Progress()):
            """Main conversion handler — called when user clicks Convert."""
            if pdf_file is None:
                gr.Warning("Please upload a PDF file first.")
                yield (
                    "❌ No file uploaded",
                    0,
                    "Please upload a PDF file to begin.",
                    gr.update(visible=False),
                    gr.update(visible=False),
                    gr.update(visible=False, value=""),
                )
                return

            filename = "document.pdf"
            pipeline = ConversionPipeline()
            tracker = ProgressTracker(job_id="active", total_pages=0)

            # Setup real-time queue for streaming updates to UI
            update_queue: asyncio.Queue[PageUpdate] = asyncio.Queue()
            loop = asyncio.get_running_loop()

            def on_page_update(update: PageUpdate):
                loop.call_soon_threadsafe(update_queue.put_nowait, update)

            tracker.register_callback(on_page_update)

            # Initial state
            log_entries: list[str] = [
                "🚀 Starting conversion pipeline...",
                "📄 Initializing PDF parser and Ollama Vision model...",
            ]
            
            yield (
                "🔄 Initializing conversion...",
                0,
                "\n".join(log_entries),
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(visible=False, value=""),
            )

            # Start pipeline task in background
            pipeline_task = asyncio.create_task(
                pipeline.run(
                    pdf_content=pdf_file,
                    pdf_filename=filename,
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
                PageStatus.COMPLETED: "✅",
                PageStatus.FALLBACK: "⚠️",
                PageStatus.FAILED: "❌",
            }

            # Live streaming loop while pipeline runs
            while not pipeline_task.done():
                try:
                    update: PageUpdate = await asyncio.wait_for(update_queue.get(), timeout=0.3)
                    icon = icon_map.get(update.status, "ℹ️")
                    time_str = f" ({update.processing_time:.1f}s)" if update.processing_time > 0 else ""
                    
                    log_line = f"{icon} Page {update.page_number + 1:2d}: {update.message}{time_str}"
                    log_entries.append(log_line)
                    
                    status_str = f"Processing: {tracker.progress_text}"
                    pct = tracker.progress_percent

                    # Check if intermediate PPT exists for partial download
                    partial_file = None
                    if pipeline.ppt_service and pipeline.storage_service:
                        # If at least 1 page completed
                        pass

                    yield (
                        status_str,
                        pct,
                        "\n".join(log_entries[-30:]),
                        gr.update(visible=False),
                        gr.update(visible=False),
                        gr.update(visible=False, value=""),
                    )
                except asyncio.TimeoutError:
                    # Periodic heartbeat to keep UI responsive
                    if tracker.total_pages > 0:
                        status_str = f"Processing: {tracker.progress_text}"
                        pct = tracker.progress_percent
                        yield (
                            status_str,
                            pct,
                            "\n".join(log_entries[-30:]),
                            gr.update(visible=False),
                            gr.update(visible=False),
                            gr.update(visible=False, value=""),
                        )

            # Drain remaining items in queue
            while not update_queue.empty():
                update = update_queue.get_nowait()
                icon = icon_map.get(update.status, "ℹ️")
                time_str = f" ({update.processing_time:.1f}s)" if update.processing_time > 0 else ""
                log_entries.append(f"{icon} Page {update.page_number + 1:2d}: {update.message}{time_str}")

            job = await pipeline_task
            register_job(job)

            pptx_path = job.pptx_path
            pptx_exists = Path(pptx_path).exists() if pptx_path else False

            log_entries.append("=" * 40)
            if job.status == "completed" and pptx_exists:
                log_entries.append(f"🎉 Complete! Processed {job.processed_pages}/{job.total_pages} pages.")
                status_text = f"✅ Conversion complete! {job.processed_pages}/{job.total_pages} pages processed."
                yield (
                    status_text,
                    100,
                    "\n".join(log_entries),
                    gr.update(visible=False),
                    gr.update(visible=True, value=pptx_path),
                    gr.update(visible=True, value=job.output_dir),
                )
            elif pptx_exists:
                log_entries.append(f"⚠️ Completed with fallback/partial slides ({job.processed_pages}/{job.total_pages} pages).")
                status_text = f"⚠️ Completed with errors. {job.processed_pages}/{job.total_pages} pages."
                yield (
                    status_text,
                    100,
                    "\n".join(log_entries),
                    gr.update(visible=False),
                    gr.update(visible=True, value=pptx_path),
                    gr.update(visible=True, value=job.output_dir),
                )
            else:
                log_entries.append("❌ Conversion failed. Check above errors.")
                status_text = "❌ Conversion failed. Check logs for details."
                yield (
                    status_text,
                    0,
                    "\n".join(log_entries),
                    gr.update(visible=False),
                    gr.update(visible=False),
                    gr.update(visible=False, value=""),
                )

        # Wire up the convert button
        convert_btn.click(
            fn=convert_pdf,
            inputs=[pdf_input, workers_slider, dpi_dropdown, quality_slider],
            outputs=[
                progress_text,
                progress_bar,
                processing_log,
                partial_download,
                final_download,
                output_path_text,
            ],
        )

    return demo
