"""AutoGrantED entrypoint."""
from __future__ import annotations
import os
import gradio as gr
from pipeline import app, demo

app = gr.mount_gradio_app(app, demo, path="/")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 7860)))
