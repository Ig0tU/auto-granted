"""
AutoGrantED — Hugging Face Spaces / Local entrypoint
====================================================
FastAPI backend + Gradio UI
SignalMesh 72-slot spatial routing · SEC-Ω PAPPG Warden · Live Grants.gov
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

from engine import (
    GrantsGovScout,
    LifecycleMonitor,
    ProposalCompiler,
    SecOmegaEngine,
    SpatialSignalMesh,
    mesh,
    monitor,
    scout,
)

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="AutoGrantED Orchestration Engine",
    description="Zero-token grant discovery, SEC-Ω compliance, SignalMesh routing & document export",
    version="2.1.0",
)


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
        "service": "AutoGrantED",
        "mesh_signals": sum(len(s) for s in mesh.grid.values()),
        "tracked_submissions": len(monitor.submissions),
    }


@app.get("/api/mesh/status")
async def mesh_status():
    return mesh.get_grid_summary()


@app.post("/api/discovery/run")
async def run_discovery(req: SearchRequest):
    hits = scout.fetch(
        keywords=req.keywords,
        agencies=req.agencies,
        rows=req.rows,
    )
    if not hits:
        hits = scout.fallback_hits(req.keywords)

    dispatched = []
    for hit in hits:
        opp_id = hit.get("id") or hit.get("number") or f"GEN-{int(time.time())}"
        agency = str(hit.get("agencyCode", "FED")).upper()
        uri = f"grantsgov://{agency.lower()}/{opp_id}"

        envelope = mesh.emit(
            uri=uri,
            payload=hit,
            frequencies=["opp-raw", "grant-active"],
        )
        dispatched.append(
            {
                "uri": uri,
                "slot": envelope.slot,
                "title": hit.get("title"),
                "agency": agency,
                "close_date": hit.get("closeDate"),
            }
        )

    return {
        "status": "SUCCESS",
        "ingested_count": len(dispatched),
        "signals": dispatched,
        "mesh_summary": mesh.get_grid_summary(),
    }


@app.post("/api/proposals/validate-and-export")
async def validate_and_export(req: ProposalRequest):
    # Inject agency + title into draft for the warden
    draft = dict(req.draft)
    draft["agency"] = req.agency
    draft.setdefault("formatting", {
        "font_family": "Times New Roman",
        "font_size": 11.0,
        "margin_inches": 1.0,
    })

    audit = SecOmegaEngine.audit(draft)

    if not audit["is_valid"]:
        mesh.emit(
            uri=f"grant://{req.agency.lower()}/{req.submission_id}/rejection",
            payload=audit,
            frequencies=["rejection-audit"],
        )
        return {"status": "REJECTED", "audit": audit}

    sections = draft.get("sections", {}) or {}
    manifest = {
        "compiled_artifacts": {
            "cover_sheet": {"proposal_title": req.title},
            "summary": sections.get("project_summary", {}),
            "core_narrative": (sections.get("project_description") or {}).get(
                "content", ""
            ),
            "data_management_plan": sections.get(
                "data_management_plan",
                "All datasets and telemetry published under FAIR open-access protocols.",
            ),
        }
    }

    tex_path = ProposalCompiler.compile_latex(req.submission_id, manifest)
    docx_path = ProposalCompiler.compile_docx(req.submission_id, manifest)

    mesh.emit(
        uri=f"grant://{req.agency.lower()}/{req.submission_id}/approved",
        payload={
            "manifest": manifest,
            "tex_path": tex_path,
            "docx_path": docx_path,
        },
        frequencies=["pkg-ready", "submission-status"],
    )

    # Register lifecycle
    monitor.track(req.submission_id, agency=req.agency)

    return {
        "status": "APPROVED",
        "audit": audit,
        "artifacts": {
            "latex_path": tex_path,
            "docx_path": docx_path,
        },
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


# ---------------------------------------------------------------------------
# Gradio UI helpers
# ---------------------------------------------------------------------------

def gui_discovery(keywords: str, agencies: str, rows: int = 5):
    hits = scout.fetch(keywords=keywords, agencies=agencies, rows=int(rows))
    if not hits:
        hits = scout.fallback_hits(keywords)

    lines = []
    for hit in hits:
        opp_id = hit.get("id") or hit.get("number") or "GEN"
        agency = str(hit.get("agencyCode", "FED")).upper()
        uri = f"grantsgov://{agency.lower()}/{opp_id}"
        env = mesh.emit(uri, hit, ["opp-raw", "grant-active"])
        lines.append(
            f"Slot [{env.slot:02d}]  ·  {agency}  ·  {hit.get('title', 'Untitled')}"
        )

    summary = mesh.get_grid_summary()
    return "\n".join(lines) or "No opportunities found.", json.dumps(summary, indent=2)


def gui_audit_export(
    title: str,
    agency: str,
    overview: str,
    merit: str,
    broader: str,
    narrative: str,
    dmp: str,
):
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
            "project_description": {
                "estimated_pages": 14,
                "content": narrative,
            },
            "data_management_plan": dmp or "FAIR-compliant open repository.",
        },
    }

    audit = SecOmegaEngine.audit(draft)
    if not audit["is_valid"]:
        err_text = "REJECTED BY SEC-Ω\n\n" + "\n".join(f"• {e}" for e in audit["errors"])
        if audit["warnings"]:
            err_text += "\n\nWarnings:\n" + "\n".join(f"• {w}" for w in audit["warnings"])
        return err_text, None, None

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

    mesh.emit(
        uri=f"grant://{agency.lower()}/{sub_id}/approved",
        payload={"tex": tex_path, "docx": docx_path},
        frequencies=["pkg-ready", "submission-status"],
    )
    monitor.track(sub_id, agency=agency)

    status = (
        f"APPROVED BY SEC-Ω WARDEN\n"
        f"Submission ID: {sub_id}\n"
        f"Agency: {agency}\n"
        f"Warnings: {len(audit.get('warnings', []))}"
    )
    return status, tex_path, docx_path


def gui_mesh_clear():
    mesh.clear()
    return "Mesh cleared.", json.dumps(mesh.get_grid_summary(), indent=2)


# ---------------------------------------------------------------------------
# Gradio Blocks
# ---------------------------------------------------------------------------

with gr.Blocks(
    title="AutoGrantED · SignalMesh Orchestrator",
    theme=gr.themes.Soft(primary_hue="indigo", secondary_hue="slate"),
    css="""
    .gradio-container { max-width: 1100px !important; }
    footer { visibility: hidden; }
    """,
) as demo:
    gr.Markdown(
        """
        # AutoGrantED
        **Zero-token grant discovery · SignalMesh 72-slot spatial routing · SEC-Ω PAPPG / DARPA compliance**

        Live Grants.gov ingestion → deterministic mesh hydration → compliance firewall → LaTeX / DOCX export.
        """
    )

    with gr.Tab("1 · Opportunity Discovery"):
        with gr.Row():
            kw = gr.Textbox(
                label="Keywords",
                value="smart grid signal mesh edge AI orchestration",
                scale=3,
            )
            ag = gr.Textbox(label="Agencies", value="NSF|DARPA|DOE", scale=1)
            rows = gr.Slider(1, 15, value=5, step=1, label="Max results")
        scan_btn = gr.Button("Scan Grants.gov & Broadcast to Mesh", variant="primary")
        with gr.Row():
            scan_log = gr.Textbox(label="Dispatched Spatial Signals", lines=8, interactive=False)
            mesh_state = gr.Code(label="SignalMesh Grid State", language="json")
        clear_btn = gr.Button("Clear Mesh", variant="secondary")
        scan_btn.click(gui_discovery, inputs=[kw, ag, rows], outputs=[scan_log, mesh_state])
        clear_btn.click(gui_mesh_clear, outputs=[scan_log, mesh_state])

    with gr.Tab("2 · SEC-Ω Audit & Export"):
        title_in = gr.Textbox(
            label="Proposal Title",
            value="SignalMesh: Zero-Token Ambient Multi-Agent Orchestration for Smart Grids",
        )
        agency_in = gr.Dropdown(
            label="Target Agency",
            choices=["NSF", "DARPA", "DOE"],
            value="NSF",
        )
        with gr.Row():
            overview_in = gr.Textbox(
                label="Overview",
                lines=3,
                value="Integration of spatial frequency routing for distributed smart-grid nodes with deterministic 72-cell context propagation.",
            )
            merit_in = gr.Textbox(
                label="Intellectual Merit",
                lines=3,
                value="Replaces vector-retrieval overhead with SHA-256 spatial indexing at 1.69 µs latency, achieving 96 % token reduction across multi-agent orchestration.",
            )
        broader_in = gr.Textbox(
            label="Broader Impacts",
            lines=2,
            value="Dramatically reduces edge-computing carbon footprint and stabilizes renewable microgrids across municipal and industrial deployments.",
        )
        narrative_in = gr.Textbox(
            label="Project Description / Narrative",
            lines=6,
            value=(
                "This project develops a deterministic SignalMesh fabric that hydrates "
                "agent context before inference, eliminating expensive tool-call loops. "
                "Work packages cover antenna-model design, spatial index formalization, "
                "SEC-Ω compliance gate, and real-time KPI telemetry for post-award monitoring. "
                "Broader Impacts include open-source release of the 72-slot mesh library "
                "and community workshops on zero-token multi-agent systems."
            ),
        )
        dmp_in = gr.Textbox(
            label="Data Management Plan (summary)",
            lines=2,
            value="All code, telemetry traces, and benchmark datasets published under FAIR principles in a public GitHub + Hugging Face repository with DOI minting.",
        )
        compile_btn = gr.Button("Run SEC-Ω Audit & Compile Package", variant="primary")
        status_out = gr.Textbox(label="SEC-Ω Status", lines=5, interactive=False)
        with gr.Row():
            tex_out = gr.File(label="LaTeX Source (.tex)")
            docx_out = gr.File(label="Word Document (.docx)")
        compile_btn.click(
            gui_audit_export,
            inputs=[title_in, agency_in, overview_in, merit_in, broader_in, narrative_in, dmp_in],
            outputs=[status_out, tex_out, docx_out],
        )

    with gr.Tab("3 · Lifecycle & API"):
        gr.Markdown(
            """
            ### REST Endpoints
            | Method | Path | Description |
            |--------|------|-------------|
            | GET | `/api/health` | Service health |
            | GET | `/api/mesh/status` | 72-slot grid summary |
            | POST | `/api/discovery/run` | Live Grants.gov sweep |
            | POST | `/api/proposals/validate-and-export` | SEC-Ω + compile |
            | GET | `/api/download/{filename}` | Download artifact |
            | GET | `/api/lifecycle` | Tracked submissions |

            Full OpenAPI docs available at `/docs` when running under uvicorn.
            """
        )
        refresh_btn = gr.Button("Refresh Lifecycle Registry")
        lifecycle_out = gr.Code(label="Tracked Submissions", language="json")
        refresh_btn.click(
            lambda: json.dumps(monitor.list_submissions(), indent=2),
            outputs=[lifecycle_out],
        )

    gr.Markdown(
        """
        ---
        Built with **SignalMesh** spatial indexing · SEC-Ω compliance firewall · Grants.gov Search2 API  
        Related: [signalmesh](https://github.com/Ig0tU/signalmesh) · [AutoGrantED Space](https://huggingface.co/spaces/acecalisto3/AutoGrantED)
        """
    )


# Mount Gradio on the FastAPI app (HF Spaces compatible)
app = gr.mount_gradio_app(app, demo, path="/")


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port)
