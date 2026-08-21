from __future__ import annotations
import json, os, time
from typing import Any, Dict, List, Optional
import gradio as gr
from engine import ProposalCompiler, SecOmegaEngine, mesh, monitor, scout
import ollama_cloud

def gui_export(title, agency, overview, merit, broader, narrative, dmp):
    empty = (None, None, "<p><em>No preview yet.</em></p>",
             json.dumps(monitor.list_submissions(), indent=2))
    if not title or not overview or not merit or not broader:
        return ("Select an opportunity first.", *empty)
    draft = {
        "agency": agency,
        "formatting": {"font_family": "Times New Roman",
                       "font_size": 11.0 if agency != "DARPA" else 12.0,
                       "margin_inches": 1.0},
        "sections": {
            "project_summary": {"overview": overview, "intellectual_merit": merit,
                                "broader_impacts": broader},
            "project_description": {"estimated_pages": 14, "content": narrative},
            "data_management_plan": dmp or "FAIR-compliant open repository.",
        },
    }
    audit = SecOmegaEngine.audit(draft)
    if not audit["is_valid"]:
        err = "REJECTED BY SEC-Omega\n\n" + "\n".join(f"- {e}" for e in audit["errors"])
        return err, None, None, "<p>Rejected</p>", json.dumps(monitor.list_submissions(), indent=2)
    sub_id = f"SUB-{agency}-{int(time.time())}"
    manifest = {"compiled_artifacts": {
        "cover_sheet": {"proposal_title": title},
        "summary": draft["sections"]["project_summary"],
        "core_narrative": narrative,
        "data_management_plan": draft["sections"]["data_management_plan"],
    }}
    tex_path = ProposalCompiler.compile_latex(sub_id, manifest)
    docx_path = ProposalCompiler.compile_docx(sub_id, manifest)
    if tex_path: tex_path = os.path.abspath(tex_path)
    if docx_path: docx_path = os.path.abspath(docx_path)
    monitor.track(sub_id, agency=agency)
    tex_ok = bool(tex_path and os.path.isfile(tex_path))
    docx_ok = bool(docx_path and os.path.isfile(docx_path))
    status = (f"APPROVED BY SEC-Omega\nSubmission: {sub_id}\nAgency: {agency}\n"
              f"LaTeX: {tex_path if tex_ok else 'FAILED'}\n"
              f"DOCX: {docx_path if docx_ok else 'FAILED'}")
    def esc(s):
        return (s or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace("\n","<br/>")
    preview = (f"<div style=\"font-family:Times New Roman,serif;padding:16px\">"
               f"<h2>{esc(title)}</h2><h3>Overview</h3><p>{esc(overview)}</p>"
               f"<h3>Intellectual Merit</h3><p>{esc(merit)}</p>"
               f"<h3>Broader Impacts</h3><p>{esc(broader)}</p>"
               f"<h3>Narrative</h3><p>{esc(narrative)}</p>"
               f"<h3>DMP</h3><p>{esc(dmp)}</p></div>")
    return status, (tex_path if tex_ok else None), (docx_path if docx_ok else None), preview, json.dumps(monitor.list_submissions(), indent=2)

def gui_clear():
    mesh.clear()
    return ([["-"]]*7, gr.update(choices=[], value=None),
            json.dumps(mesh.get_grid_summary(), indent=2), "Mesh cleared.", [])

def gui_lifecycle():
    return json.dumps(monitor.list_submissions(), indent=2)

def gui_validate_key(key: str):
    ok, msg = ollama_cloud.validate_key(key or "")
    models, note = ollama_cloud.models_for_grant_task(api_key=key or None)
    return msg, gr.update(choices=models, value=(models[0] if models else None)), note

def gui_refresh_models(key: str):
    models, note = ollama_cloud.models_for_grant_task(api_key=key or None)
    return gr.update(choices=models, value=(models[0] if models else None)), note

def gui_slm_generate(key, model, title, agency, overview_hint, opp_state, selection):
    if not key or not str(key).strip():
        return title or "", agency or "NSF", "", "", "", "", "", "Paste API key: https://ollama.com/settings/keys"
    if not model:
        return title or "", agency or "NSF", "", "", "", "", "", "Select a cloud model."
    opp_number, opp_title, deadline = "N/A", title or "Untitled", "N/A"
    if selection and opp_state:
        for r in opp_state:
            if f"[{r['agency']}] {r['number']} — {r['title'][:65]}" == selection:
                opp_number, opp_title, deadline, agency = r["number"], r["title"], r["close"], r["agency"]
                break
    try:
        sections = ollama_cloud.generate_proposal_sections(
            str(key).strip(), str(model).strip(),
            agency=agency or "NSF", opp_number=str(opp_number),
            opp_title=str(opp_title), deadline=str(deadline))
    except Exception as e:
        return title or opp_title, agency or "NSF", "", "", "", "", "", f"Ollama Cloud error: {e}"
    status = f"SLM draft via ollama.com model={model}\n{agency} {opp_number} · {deadline}"
    return (sections["project_title"], agency or "NSF", sections["overview"],
            sections["intellectual_merit"], sections["broader_impacts"],
            sections["narrative"], sections["dmp"], status)
