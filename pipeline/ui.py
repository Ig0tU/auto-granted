from __future__ import annotations
import gradio as gr
from pipeline.helpers import (
    gui_scan, gui_clear, gui_select, gui_export, gui_lifecycle,
    gui_validate_key, gui_refresh_models, gui_slm_generate,
)

with gr.Blocks(title="AutoGrantED") as demo:
    gr.Markdown("# AutoGrantED\n**Scan → Select → Ollama Cloud SLM → SEC-Omega → Export**")
    opp_state = gr.State([])

    gr.Markdown("### 1 · Discover")
    with gr.Row():
        kw = gr.Textbox(label="Keywords", value="smart grid signal mesh edge AI", scale=3)
        ag = gr.Textbox(label="Agencies", value="NSF|DARPA|DOE", scale=1)
        rows = gr.Slider(1, 15, value=8, step=1, label="Max results")
    with gr.Row():
        scan_btn = gr.Button("Scan Grants.gov → Mesh", variant="primary")
        clear_btn = gr.Button("Clear Mesh")
    scan_msg = gr.Textbox(label="Scan status", interactive=False)
    opp_table = gr.Dataframe(
        headers=["Slot", "Agency", "Number", "Title", "Open", "Close", "Status"],
        label="Opportunities", interactive=False, wrap=True)
    with gr.Row():
        select_dd = gr.Dropdown(label="Select opportunity → hydrate", choices=[], scale=3)
        mesh_box = gr.Code(label="Mesh grid", language="json", scale=2)

    gr.Markdown("### 2 · Ollama Cloud\n[Get API key](https://ollama.com/settings/keys) · "
                "[Cloud docs](https://docs.ollama.com/cloud) · model names **without** `-cloud`")
    with gr.Row():
        ollama_key = gr.Textbox(label="Ollama Cloud API key", type="password", scale=3)
        validate_btn = gr.Button("Validate key")
    key_status = gr.Textbox(label="Key status", interactive=False)
    with gr.Row():
        model_dd = gr.Dropdown(label="Cloud model (grant-task ranked)", choices=[], scale=3)
        refresh_models_btn = gr.Button("Refresh models")
    model_note = gr.Textbox(label="Model source", interactive=False)
    slm_btn = gr.Button("Generate sections with Ollama Cloud SLM", variant="primary")

    gr.Markdown("### 3 · Proposal")
    hydrate_status = gr.Textbox(label="Status", interactive=False)
    title_in = gr.Textbox(label="Proposal Title")
    agency_in = gr.Dropdown(label="Agency", choices=["NSF", "DARPA", "DOE"], value="NSF")
    with gr.Row():
        overview_in = gr.Textbox(label="Overview", lines=3)
        merit_in = gr.Textbox(label="Intellectual Merit", lines=3)
    broader_in = gr.Textbox(label="Broader Impacts", lines=2)
    narrative_in = gr.Textbox(label="Project Description", lines=6)
    dmp_in = gr.Textbox(label="Data Management Plan", lines=2)

    gr.Markdown("### 4 · SEC-Omega & export")
    compile_btn = gr.Button("Run SEC-Omega & Compile", variant="primary")
    status_out = gr.Textbox(label="Export status", lines=5, interactive=False)
    with gr.Row():
        tex_out = gr.File(label="LaTeX (.tex)")
        docx_out = gr.File(label="Word (.docx)")
    preview_html = gr.HTML(label="Preview")

    gr.Markdown("### 5 · Lifecycle")
    refresh_btn = gr.Button("Refresh registry")
    lifecycle_out = gr.Code(label="Submissions", language="json")

    scan_btn.click(gui_scan, [kw, ag, rows],
                   [opp_table, select_dd, mesh_box, scan_msg, opp_state])
    clear_btn.click(gui_clear, outputs=[opp_table, select_dd, mesh_box, scan_msg, opp_state])
    select_dd.change(gui_select, [select_dd, opp_state],
        [title_in, agency_in, overview_in, merit_in, broader_in, narrative_in, dmp_in, hydrate_status])
    compile_btn.click(gui_export,
        [title_in, agency_in, overview_in, merit_in, broader_in, narrative_in, dmp_in],
        [status_out, tex_out, docx_out, preview_html, lifecycle_out])
    validate_btn.click(gui_validate_key, [ollama_key], [key_status, model_dd, model_note])
    refresh_models_btn.click(gui_refresh_models, [ollama_key], [model_dd, model_note])
    slm_btn.click(gui_slm_generate,
        [ollama_key, model_dd, title_in, agency_in, overview_in, opp_state, select_dd],
        [title_in, agency_in, overview_in, merit_in, broader_in, narrative_in, dmp_in, hydrate_status])
    refresh_btn.click(gui_lifecycle, outputs=[lifecycle_out])
    demo.load(lambda: gui_refresh_models(""), outputs=[model_dd, model_note])
