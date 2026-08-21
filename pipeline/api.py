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
import ollama_cloud

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
