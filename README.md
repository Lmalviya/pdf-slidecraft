# 🎨 PDF-SlideCraft

> **Convert PDF slide scans, documents, and lecture notes into fully editable PowerPoint (.pptx) presentations locally or via cloud vision models in seconds.**

[![Python](https://img.shields.io/badge/Python-3.11-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![Gradio](https://img.shields.io/badge/Gradio-6.0+-FF5722.svg)](https://gradio.app)
[![NVIDIA NIM](https://img.shields.io/badge/NVIDIA-NIM%20Vision-76B900.svg)](https://build.nvidia.com)
[![OpenCV](https://img.shields.io/badge/OpenCV-4.8+-5C3EE8.svg)](https://opencv.org)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg)](https://docker.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## ✨ Key Features

- ⚡ **Multi-Provider Engine Support**:
  - **Local Fast Layout + OCR (Default)**: 100% offline CPU execution using RapidOCR (ONNX) + OpenCV layout analysis (~1–2s per page).
  - **NVIDIA NIM Vision API (Cloud)**: Connect free-tier NVIDIA NIM vision models (`meta/llama-3.2-11b-vision-instruct`, `meta/llama-3.2-90b-vision-instruct`) for high-precision multimodal document extraction.
  - **Local Ollama VLM**: Offline multimodal inference (e.g. `qwen2.5vl:3b`).
- 📝 **100% Editable Text & Typography**: Extracted text boxes retain titles, headings, bullet hierarchies (`•`, `1.`, `a)`, `b)`), font sizes, and alignments.
- 🖼️ **Intelligent Image & Diagram Extraction**: OpenCV edge contour analysis automatically locates, crops, and embeds diagrams, medical images, and figures at exact coordinates.
- 🛡️ **Rate Limiting & Automatic Fallback**: Built-in sliding-window rate limiting (RPM + concurrency). If cloud API quotas or network errors occur, the pipeline automatically falls back to the local OCR engine so conversion never fails.
- 🚀 **1-Click Startup & Graceful Stop**:
  - Double-click **`start.bat`** (Docker) or **`run_local.bat`** (Native Python).
  - When closing the terminal or pressing `Ctrl+C`, all containers and processes stop cleanly without deleting images, models, or output data.
- 📊 **Real-Time Streaming UI**: Interactive Gradio web interface with live progress indicators and streaming structured logs.

---

## 🏗️ Architecture

```
                                  ┌──────────────────────────────┐
                                  │   PDF Document / Slide Scan  │
                                  └──────────────┬───────────────┘
                                                 │
                                                 ▼
                                     [ PyMuPDF Page Renderer ]
                                                 │
         ┌───────────────────────────────────────┼───────────────────────────────────────┐
         ▼                                       ▼                                       ▼
  [ ⚡ Local OCR Engine ]              [ ☁️ NVIDIA NIM Vision API ]             [ 🦙 Ollama VLM Engine ]
   • RapidOCR (ONNX CPU)                • Llama 3.2 11B / 90B Vision            • Qwen 2.5-VL (Local)
   • OpenCV Edge Layout                 • HTML Structured Layout                • HTML Structured Layout
   • Figure / Photo Cropping            • Rate Limiter + Auto Fallback          • Local Offline Fallback
         │                                       │                                       │
         └───────────────────────────────────────┼───────────────────────────────────────┘
                                                 │
                                                 ▼
                                     [ PPT Generation Service ]
                                      • Multi-level Bullet Formatting
                                      • Pixel-Perfect Image Cropping
                                      • Widescreen 16:9 Slide Output
                                                 │
                                                 ▼
                                  ┌──────────────────────────────┐
                                  │   Editable PowerPoint .pptx  │
                                  └──────────────────────────────┘
```

---

## 🚀 Quick Start

### Option 1: Docker (Recommended)
1. Ensure [Docker Desktop](https://www.docker.com/products/docker-desktop/) is running.
2. Double-click **`start.bat`** (or run `docker compose up -d --build`).
3. Your browser will automatically open to **`http://localhost:7860`**.
4. *To stop:* Press `Ctrl+C` or close the terminal — all containers will be stopped gracefully.

### Option 2: Native Python
1. Ensure Python 3.10+ is installed.
2. Double-click **`run_local.bat`** (or execute manually):
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   python -m uvicorn app.main:app --host 127.0.0.1 --port 7860
   ```
3. Open **`http://localhost:7860`** in your browser.

---

## 💻 Web Interface Guide

| Setting | Description |
|:---|:---|
| **⚡ Engine Selector** | Switch between `Local Fast Layout + OCR`, `NVIDIA NIM Vision Cloud API`, or `Local Ollama VLM`. |
| **☁️ NVIDIA API Key** | Enter your free API key (`nvapi-...`) from [build.nvidia.com](https://build.nvidia.com) (masked for security). |
| **🤖 NVIDIA Model** | Select between `Llama 3.2 11B Vision` (Fast & sharp) or `Llama 3.2 90B Vision` (Complex multi-column decks). |
| **⚙️ Advanced Settings** | Configure parallel page workers (default: 2), rendering DPI (default: 150), and image export quality. |
| **⬇️ Downloads** | Click the direct download button upon completion to receive the fully formatted `.pptx` file. |

---

## 📂 Project Structure

```
├── app/
│   ├── main.py                # FastAPI entry point & routes
│   ├── config.py              # Application settings & environment variables
│   ├── agents/
│   │   ├── graph.py           # Pipeline orchestration & batch page workers
│   │   ├── nodes.py           # Multi-engine routing & fallback workflow
│   │   └── callbacks.py       # Real-time UI progress callback tracker
│   ├── services/
│   │   ├── ocr_service.py     # RapidOCR (ONNX Runtime) CPU line extractor
│   │   ├── layout_service.py  # OpenCV edge morphology & image detector
│   │   ├── nvidia_service.py  # NVIDIA NIM Vision API client with rate limiting
│   │   ├── vlm_service.py     # Local Ollama VLM client
│   │   ├── html_parser_service.py # HTML layout & coordinate parser
│   │   ├── pdf_service.py     # PyMuPDF rendering & digital vector text extraction
│   │   ├── ppt_service.py     # python-pptx editable slide constructor
│   │   └── storage_service.py # File lifecycle & directory manager
│   ├── core/
│   │   ├── rate_limiter.py    # Async concurrency & sliding-window RPM limiter
│   │   └── logging_config.py  # Structured JSON / console logger
│   ├── models/                # Pydantic schemas, bounding boxes, element types
│   └── utils/                 # Coordinate mappers, image helpers, file utilities
├── frontend/
│   └── gradio_ui.py           # Interactive Gradio web interface
├── tests/                     # Automated test suites (OCR, layout, NVIDIA, parser)
├── docker-compose.yml         # Container orchestration
├── Dockerfile                 # Production Docker image
├── start.bat                  # 1-click Docker startup & clean shutdown script
├── run_local.bat              # 1-click native Python startup script
└── requirements.txt           # Python dependencies
```

---

## ⚙️ Configuration Options

Configuration can be set in `.env` (copy from `.env.example`):

| Variable | Default | Description |
|:---|:---|:---|
| `DEFAULT_ENGINE` | `local_ocr` | Default engine (`local_ocr`, `nvidia_api`, `local_vlm`) |
| `NVIDIA_API_KEY` | `None` | NVIDIA NIM API key (`nvapi-...`) |
| `NVIDIA_DEFAULT_MODEL` | `meta/llama-3.2-11b-vision-instruct` | Default NVIDIA Vision model |
| `NVIDIA_RPM_LIMIT` | `30` | Max requests per minute for NVIDIA API |
| `NVIDIA_CONCURRENCY_LIMIT` | `2` | Max concurrent requests to NVIDIA API |
| `MAX_PARALLEL_WORKERS` | `2` | Concurrent page workers |
| `DEFAULT_DPI` | `150` | PDF rendering resolution (optimal balance of speed & quality) |
| `DEFAULT_IMAGE_QUALITY`| `85` | JPEG quality for cropped figures and photos |
| `APP_PORT` | `7860` | Web UI & API port |
| `LOG_LEVEL` | `INFO` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
