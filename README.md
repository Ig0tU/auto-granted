# AutoGrantED

**Zero-token grant discovery, orchestration, compliance & export engine**

Powered by **SignalMesh** 72-slot spatial frequency routing and the **SEC-Ω** PAPPG / DARPA compliance warden.

[![Hugging Face Spaces](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Spaces-blue)](https://huggingface.co/spaces/acecalisto3/AutoGrantED)

---

## What it does

1. **Discovers** live opportunities from Grants.gov (NSF, DARPA, DOE, …)
2. **Routes** them through a deterministic 72-slot SignalMesh grid (`SHA-256(uri) % 72`)
3. **Hydrates** agent context at microsecond latency (no vector DB, no tool-call loops)
4. **Validates** proposals against NSF PAPPG and DARPA BAA rules via the SEC-Ω firewall
5. **Compiles** submission-ready LaTeX + DOCX packages with 1-inch margins, 11 pt Times New Roman
6. **Tracks** lifecycle state and post-award KPI telemetry

## Quick start (local)

```bash
git clone https://github.com/Ig0tU/auto-granted.git
cd auto-granted
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

- Gradio UI → http://localhost:7860  
- FastAPI docs → http://localhost:7860/docs  
- Mesh status → http://localhost:7860/api/mesh/status  

## Hugging Face Spaces

The same `app.py` is HF-Spaces ready. Set the Space to **Docker** or **Gradio** and point the entry to `app.py`.

## Architecture

```
Grants.gov Search2 API
        │
        ▼  #opp-raw
┌───────────────────────┐
│  SignalMesh Hub       │  72-slot spatial grid
│  (SHA-256 % 72)       │
└───────────┴───────────┘
            │
    ┌───────┴───────┐
    ▼               ▼
SEC-Ω Warden   Context Hydrator
    │
    ▼  #pkg-ready
Document Compiler (LaTeX / DOCX)
    │
    ▼  #submission-status
Lifecycle Monitor + KPI telemetry
```

## Core modules

| File        | Responsibility                                      |
|-------------|-----------------------------------------------------|
| `engine.py` | SignalMesh, SEC-Ω, Grants.gov scout, compiler, monitor |
| `app.py`    | FastAPI routes + Gradio UI                          |

## SignalMesh integration

AutoGrantED is designed to interoperate with the standalone SignalMesh runtime:

- https://github.com/Ig0tU/signalmesh  
- https://huggingface.co/spaces/acecalisto3/signalmesh  
- https://kyklos.io (Antennae Model / Spatial Signal Indexing)

Agents subscribe to frequency bands (`#opp-raw`, `#grant-active`, `#draft-review`, `#pkg-ready`, …). Context is hydrated **before** inference, cutting token spend by ~96 %.

## Example SEC-Ω rules enforced

**NSF PAPPG**
- 1.0 inch margins
- Allowed fonts + minimum sizes (Times New Roman ≥ 11 pt, etc.)
- Project Summary must contain Overview / Intellectual Merit / Broader Impacts
- Project Description ≤ 15 pages
- Data Management Plan required

**DARPA BAA**
- Minimum 12 pt font
- Volume I (Technical) + Volume II (Cost) structure
- Mandatory admin fields (BAA number, UEI, …)

## License

MIT — build, fork, and ship.
