"""
AutoGrantED — FastAPI + Gradio
Scan → Select → Auto-hydrate → SEC-Ω → Export → Track
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional

import gradio as gr
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from engine import ProposalCompiler, SecOmegaEngine, mesh, monitor, scout

app = FastAPI(title="AutoGrantED", version="2.2.0")


class SearchRequest(BaseModel):
    keywords: str = "smart grid signal mesh AI"
    agencies: str = "NSF|DARPA|DOE"
    rows: int = Field(default=5, ge=1, le=25)


class ProposalRequest(BaseModel):
    submission_id: str
    agency: str = "NSF"
    title: str = "SignalMesh Infrastructure Deployment"
    draft: Dict[str, Any]


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "mesh_signals": sum(len(s) for s in mesh.grid.values()),
        "tracked_submissions": len(monitor.submissions),
    }


@app.get("/api/mesh/status")
async def mesh_status():
    return mesh.get_grid_summary()


@app.post("/api/discovery/run")
async def run_discovery(req: SearchRequest):
    hits = scout.fetch(keywords=req.keywords, agencies=req.agencies, rows=req.rows)
    if not hits:
        hits = scout.fallback_hits(req.keywords)
    dispatched = []
    for hit in hits:
        opp_id = hit.get("id") or hit.get("number") or f"GEN-{int(time.time())}"
        agency = str(hit.get("agencyCode", "FED")).upper()
        uri = f"grantsgov://{agency.lower()}/{opp_id}"
        env = mesh.emit(uri, hit, ["opp-raw", "grant-active"])
        dispatched.append({
            "uri": uri, "slot": env.slot, "title": hit.get("title"),
            "agency": agency, "close_date": hit.get("closeDate"),
            "number": hit.get("number"),
        })
    return {"status": "SUCCESS", "ingested_count": len(dispatched),
            "signals": dispatched, "mesh_summary": mesh.get_grid_summary()}


@app.post("/api/proposals/validate-and-export")
async def validate_and_export(req: ProposalRequest):
    draft = dict(req.draft)
    draft["agency"] = req.agency
    draft.setdefault("formatting", {
        "font_family": "Times New Roman", "font_size": 11.0, "margin_inches": 1.0,
    })
    audit = SecOmegaEngine.audit(draft)
    if not audit["is_valid"]:
        return {"status": "REJECTED", "audit": audit}
    sections = draft.get("sections", {}) or {}
    manifest = {
        "compiled_artifacts": {
            "cover_sheet": {"proposal_title": req.title},
            "summary": sections.get("project_summary", {}),
            "core_narrative": (sections.get("project_description") or {}).get("content", ""),
            "data_management_plan": sections.get(
                "data_management_plan",
                "FAIR open-access repository protocols.",
            ),
        }
    }
    tex_path = ProposalCompiler.compile_latex(req.submission_id, manifest)
    docx_path = ProposalCompiler.compile_docx(req.submission_id, manifest)
    monitor.track(req.submission_id, agency=req.agency)
    return {
        "status": "APPROVED", "audit": audit,
        "artifacts": {"latex_path": tex_path, "docx_path": docx_path},
        "submission_id": req.submission_id,
    }


@app.get("/api/download/{filename}")
async def download_file(filename: str):
    path = os.path.join(ProposalCompiler.EXPORT_DIR, filename)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path, filename=filename)


@app.get("/api/lifecycle")
async def list_lifecycle():
    return {"submissions": monitor.list_submissions()}


# ── Gradio pipeline ────────────────────────────────────────────────────────

def _normalize(hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = []
    for hit in hits:
        opp_id = str(hit.get("id") or hit.get("number") or "GEN")
        agency = str(hit.get("agencyCode", "FED")).upper()
        uri = f"grantsgov://{agency.lower()}/{opp_id}"
        env = mesh.emit(uri, hit, ["opp-raw", "grant-active"])
        rows.append({
            "slot": env.slot,
            "agency": agency,
            "number": hit.get("number") or opp_id,
            "title": hit.get("title") or "Untitled",
            "open": hit.get("openDate") or "-",
            "close": hit.get("closeDate") or "-",
            "status": hit.get("oppStatus") or "posted",
            "id": opp_id,
            "agency_name": hit.get("agencyName") or agency,
        })
    return rows


def gui_scan(keywords: str, agencies: str, rows: float):
    n = int(rows)
    hits = scout.fetch(keywords=keywords, agencies=agencies, rows=n)
    source = "live"
    if not hits:
        hits = scout.fallback_hits(keywords)
        source = "fallback"
    norm = _normalize(hits)
    if not norm:
        return (
            [["-", "-", "-", "No hits", "-", "-", "-"]],
            gr.update(choices=[], value=None),
            json.dumps(mesh.get_grid_summary(), indent=2),
            f"No hits for '{keywords}'.",
            [],
        )
    table = [[r["slot"], r["agency"], r["number"],
              r["title"][:85] + ("..." if len(r["title"]) > 85 else ""),
              r["open"], r["close"], r["status"]] for r in norm]
    labels = [f"[{r['agency']}] {r['number']} — {r['title'][:65]}" for r in norm]
    summary = mesh.get_grid_summary()
    msg = (f"Ingested {len(norm)} ({source}) | "
           f"{summary['total_signals']} signals | "
           f"{len(summary['populated_slots'])} slots")
    return (
        table,
        gr.update(choices=labels, value=labels[0]),
        json.dumps(summary, indent=2),
        msg,
        norm,
    )


def gui_select(selection: Optional[str], opps: List[Dict[str, Any]]):
    if not selection or not opps:
        return ("", "NSF", "", "", "", "", "", "Scan, then pick an opportunity.")
    chosen = None
    for r in opps:
        if f"[{r['agency']}] {r['number']} — {r['title'][:65]}" == selection:
            chosen = r
            break
    if chosen is None:
        chosen = opps[0]

    agency, title, number, close = (
        chosen["agency"], chosen["title"], chosen["number"], chosen["close"]
    )
    aname = chosen.get("agency_name") or agency

    overview = (
        f"This project responds to {agency} opportunity {number} (\"{title}\"). "
        f"We deploy SignalMesh — a deterministic 72-slot spatial frequency fabric — "
        f"for zero-token multi-agent orchestration aligned with the solicitation. "
        f"Deadline: {close}."
    )
    merit = (
        f"Intellectual Merit: SHA-256 spatial indexing (uri % 72) hydrates agent "
        f"context in ~1.69 us, cutting ~96% tokens while SEC-Omega enforces {agency} "
        f"evaluation rules (margins, fonts, mandatory sections, page caps)."
    )
    broader = (
        f"Broader Impacts: Open SignalMesh + AutoGrantED release; lower edge/AI "
        f"energy cost; reusable patterns for infrastructure and logistics communities "
        f"served by {aname}."
    )
    narrative = (
        f"Technical Approach for {agency} {number}:\n\n"
        f"1. Discovery — Grants.gov ingestion into SignalMesh grid.\n"
        f"2. Context hydration — frequency bands (#opp-raw, #grant-active, "
        f"#draft-review, #pkg-ready) pre-load specs before inference.\n"
        f"3. SEC-Omega gate — write-time PAPPG/BAA validation.\n"
        f"4. Artifact compile — 1-inch margins, 11pt Times New Roman LaTeX/DOCX.\n"
        f"5. Lifecycle telemetry — latency, packet delivery, burn-rate KPIs.\n\n"
        f"Work Packages: WP1 Mesh core | WP2 Compliance schemas | WP3 Compiler | "
        f"WP4 Pilot dashboard | WP5 Open release & workshops.\n\n"
        f"Broader Impacts: Public code and FAIR data for {aname} proposers.\n\n"
        f"Results from Prior Support: (complete with PI history if applicable.)"
    )
    dmp = (
        "Code, telemetry, and artifacts deposited in public GitHub + Hugging Face "
        "under a permissive license with DOI/FAIR metadata. Sensitive partner data "
        "under institutional DUA controls."
    )
    status = (
        f"Hydrated from slot {chosen['slot']} · {agency} {number}\n"
        f"Close: {close}\nEdit freely, then run SEC-Omega."
    )
    return title, agency, overview, merit, broader, narrative, dmp, status


def gui_export(title, agency, overview, merit, broader, narrative, dmp):
    if not title or not overview or not merit or not broader:
        return ("Select an opportunity first (Overview / Merit / Impacts required).",
                None, None, json.dumps(monitor.list_submissions(), indent=2))
    draft = {
        "agency": agency,
        "formatting": {
            "font_family": "Times New Roman",
            "font_size": 11.0 if agency != "DARPA" else 12.0,
            "margin_inches": 1.0,
        },
        "sections": {
            "project_summary": {
                "overview": overview,
                "intellectual_merit": merit,
                "broader_impacts": broader,
            },
            "project_description": {"estimated_pages": 14, "content": narrative},
            "data_management_plan": dmp or "FAIR-compliant open repository.",
        },
    }
    audit = SecOmegaEngine.audit(draft)
    if not audit["is_valid"]:
        err = "REJECTED BY SEC-Omega\n\n" + "\n".join(f"- {e}" for e in audit["errors"])
        return err, None, None, json.dumps(monitor.list_submissions(), indent=2)

    sub_id = f"SUB-{agency}-{int(time.time())}"
    manifest = {
        "compiled_artifacts": {
            "cover_sheet": {"proposal_title": title},
            "summary": draft["sections"]["project_summary"],
            "core_narrative": narrative,
            "data_management_plan": draft["sections"]["data_management_plan"],
        }
    }
    tex_path = ProposalCompiler.compile_latex(sub_id, manifest)
    docx_path = ProposalCompiler.compile_docx(sub_id, manifest)
    monitor.track(sub_id, agency=agency)
    status = (
        f"APPROVED BY SEC-Omega\nSubmission: {sub_id}\nAgency: {agency}\n"
        f"Warnings: {len(audit.get('warnings', []))}\nDownload artifacts below."
    )
    return status, tex_path, docx_path, json.dumps(monitor.list_submissions(), indent=2)


def gui_clear():
    mesh.clear()
    return (
        [["-", "-", "-", "Mesh cleared", "-", "-", "-"]],
        gr.update(choices=[], value=None),
        json.dumps(mesh.get_grid_summary(), indent=2),
        "Mesh cleared.",
        [],
    )


def gui_lifecycle():
    return json.dumps(monitor.list_submissions(), indent=2)


with gr.Blocks(title="AutoGrantED") as demo:
    gr.Markdown(
        "# AutoGrantED\n"
        "**Scan → Select → Auto-hydrate → SEC-Omega audit → Export → Track**"
    )
    opp_state = gr.State([])

    gr.Markdown("### 1 · Discover")
    with gr.Row():
        kw = gr.Textbox(label="Keywords",
                        value="smart grid signal mesh edge AI orchestration", scale=3)
        ag = gr.Textbox(label="Agencies", value="NSF|DARPA|DOE", scale=1)
        rows = gr.Slider(1, 15, value=8, step=1, label="Max results")
    with gr.Row():
        scan_btn = gr.Button("Scan Grants.gov → Mesh", variant="primary")
        clear_btn = gr.Button("Clear Mesh")
    scan_msg = gr.Textbox(label="Scan status", interactive=False)
    opp_table = gr.Dataframe(
        headers=["Slot", "Agency", "Number", "Title", "Open", "Close", "Status"],
        label="Opportunities in mesh", interactive=False, wrap=True,
    )
    with gr.Row():
        select_dd = gr.Dropdown(
            label="Select opportunity → auto-fills proposal below",
            choices=[], interactive=True, scale=3,
        )
        mesh_box = gr.Code(label="Mesh grid", language="json", scale=2)

    gr.Markdown("### 2 · Proposal (templated from selection — edit freely)")
    hydrate_status = gr.Textbox(label="Hydration status", interactive=False)
    title_in = gr.Textbox(label="Proposal Title")
    agency_in = gr.Dropdown(label="Target Agency",
                            choices=["NSF", "DARPA", "DOE"], value="NSF")
    with gr.Row():
        overview_in = gr.Textbox(label="Overview", lines=4)
        merit_in = gr.Textbox(label="Intellectual Merit", lines=4)
    broader_in = gr.Textbox(label="Broader Impacts", lines=3)
    narrative_in = gr.Textbox(label="Project Description", lines=8)
    dmp_in = gr.Textbox(label="Data Management Plan", lines=2)

    gr.Markdown("### 3 · SEC-Omega audit & export")
    compile_btn = gr.Button("Run SEC-Omega & Compile", variant="primary")
    status_out = gr.Textbox(label="Status", lines=5, interactive=False)
    with gr.Row():
        tex_out = gr.File(label="LaTeX (.tex)")
        docx_out = gr.File(label="Word (.docx)")

    gr.Markdown("### 4 · Lifecycle")
    refresh_btn = gr.Button("Refresh registry")
    lifecycle_out = gr.Code(label="Tracked submissions", language="json")

    scan_btn.click(gui_scan, [kw, ag, rows],
                   [opp_table, select_dd, mesh_box, scan_msg, opp_state])
    clear_btn.click(gui_clear,
                    outputs=[opp_table, select_dd, mesh_box, scan_msg, opp_state])
    select_dd.change(
        gui_select, [select_dd, opp_state],
        [title_in, agency_in, overview_in, merit_in, broader_in,
         narrative_in, dmp_in, hydrate_status],
    )
    compile_btn.click(
        gui_export,
        [title_in, agency_in, overview_in, merit_in, broader_in, narrative_in, dmp_in],
        [status_out, tex_out, docx_out, lifecycle_out],
    )
    refresh_btn.click(gui_lifecycle, outputs=[lifecycle_out])


app = gr.mount_gradio_app(app, demo, path="/")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 7860)))
