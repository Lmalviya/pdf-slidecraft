# 🎨 PDF-SlideCraft

> **Convert PDF slide scans, documents, and lecture notes into fully editable PowerPoint (.pptx) presentations locally in seconds.**

[![Python](https://img.shields.io/badge/Python-3.11-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![Gradio](https://img.shields.io/badge/Gradio-6.0+-FF5722.svg)](https://gradio.app)
[![OpenCV](https://img.shields.io/badge/OpenCV-4.8+-5C3EE8.svg)](https://opencv.org)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg)](https://docker.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## ✨ Features

- ⚡ **Ultra-Fast Local Processing** — Converts pages in **~1–2 seconds per page** on standard Intel/AMD CPUs (no GPU required).
- 📝 **100% Editable Text & Typography** — Extracted text boxes retain titles, headings, bullet hierarchies (`•`, `1.`, `a)`, `b)`), font sizes, and alignments.
- 🖼️ **Intelligent Image & Diagram Extraction** — OpenCV-powered edge contour analysis locates, crops, and embeds diagrams, medical images, and figures at exact coordinates.
- 🔒 **100% Offline & Private** — No cloud APIs, no monthly fees, no data leaves your local machine.
- 🚀 **One-Click Startup** — Windows users can launch instantly by double-clicking `start.bat` (Docker) or `run_local.bat` (native Python).
- 📊 **Real-Time Streaming UI** — Gradio web UI with live progress indicators and log streaming.

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
                        ┌────────────────────────┴────────────────────────┐
                        ▼                                                 ▼
             [ RapidOCR (ONNX Engine) ]                       [ OpenCV Layout Engine ]
              • Bounding Boxes & Text                         • Text Region Masking
              • Confidence Scoring                            • Photo / Diagram Contour Detection
              • Same-row Line Merging                         • Noise & Background Filtering
                        │                                                 │
                        └────────────────────────┬────────────────────────┘
                                                 │
                                                 ▼
                                     [ PPT Generation Service ]
                                      • Multi-level Bullet Formatting
                                      • Cropped Image Embeddings
                                      • Widescreen 16:9 Alignment
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
2. Double-click **`start.bat`** (or run `docker compose up --build`).
3. Open your browser at **`http://localhost:7860`**.

### Option 2: Native Python
1. Ensure Python 3.10+ is installed.
2. Double-click **`run_local.bat`** (or execute):
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   python -m uvicorn app.main:app --host 0.0.0.0 --port 7860
   ```
3. Open **`http://localhost:7860`** in your browser.

---

## 📂 Project Structure

```
├── app/
│   ├── main.py                # FastAPI entry point & routes
│   ├── config.py              # App configuration & settings
│   ├── agents/
│   │   ├── graph.py           # Pipeline orchestration & parallel workers
│   │   ├── nodes.py           # Page processing workflow
│   │   └── callbacks.py       # Real-time UI progress tracking
│   ├── services/
│   │   ├── ocr_service.py     # RapidOCR (ONNX Runtime) CPU extraction
│   │   ├── layout_service.py  # OpenCV edge morphology & image detection
│   │   ├── pdf_service.py     # PyMuPDF rendering & vector text extraction
│   │   ├── ppt_service.py     # python-pptx editable slide construction
│   │   └── storage_service.py # File lifecycle & directory management
│   ├── models/                # Pydantic schemas, bounding boxes, element types
│   └── utils/                 # Coordinate mappers, image helpers, file utilities
├── frontend/
│   └── gradio_ui.py           # Interactive Gradio web interface
├── tests/                     # Unit & integration test suites
├── docker-compose.yml         # Container orchestration
├── Dockerfile                 # Production multi-stage Docker image
├── start.bat                  # 1-click Docker startup script
├── run_local.bat              # 1-click native Python startup script
└── requirements.txt           # Python dependencies
```

---

## ⚙️ Configuration

Copy `.env.example` to `.env` to customize settings:

| Variable | Default | Description |
|:---|:---|:---|
| `MAX_PARALLEL_WORKERS` | `2` | Number of concurrent page workers |
| `DEFAULT_DPI` | `150` | PDF rendering resolution (150 is optimal for speed & accuracy) |
| `DEFAULT_IMAGE_QUALITY`| `85` | JPEG quality for cropped figures and photos |
| `APP_PORT` | `7860` | Web UI & API port |
| `LOG_LEVEL` | `INFO` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
