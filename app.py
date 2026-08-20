"""
AutoGrantED entrypoint — FastAPI + Gradio + Ollama Cloud
"""
from __future__ import annotations

import os

from ui_pipeline import app, demo
import gradio as gr

app = gr.mount_gradio_app(app, demo, path="/")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 7860)))
