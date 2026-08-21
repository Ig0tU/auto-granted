from __future__ import annotations
import json, os, time
from typing import Any, Dict, List, Optional
import gradio as gr
from engine import ProposalCompiler, SecOmegaEngine, mesh, monitor, scout
import ollama_cloud
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
