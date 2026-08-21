# AutoGrantED

**Zero-token grant discovery, orchestration, compliance & export engine**

Powered by **SignalMesh** 72-slot spatial frequency routing and the **SEC-Ω** PAPPG / DARPA compliance warden.

[![Hugging Face Spaces](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Spaces-blue)](https://huggingface.co/spaces/acecalisto3/AutoGrantED)

---

## What it does

1. **Discovers** live opportunities from Grants.gov (NSF, DARPA, DOE, …)
2. **Routes** them through a deterministic 72-slot SignalMesh grid (`SHA-256(uri) % 72`)
3. **Hydrates** agent context at microsecond latency (no vector DB, no tool-call loops)
4. **Drafts** proposal sections with Ollama Cloud SLMs
5. **Validates** proposals against NSF PAPPG and DARPA BAA rules via the SEC-Ω firewall
6. **Compiles** submission-ready LaTeX + DOCX + Grants.gov-oriented XML packages
7. **Submits** via official Applicant S2S V2.0 when a registered certificate is present
8. **Tracks** lifecycle state and post-award KPI telemetry

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

## Full automation suite (minimal human involvement)

```bash
# Check what is still needed from a human
python scripts/run_automation.py --readiness

# End-to-end: discover → draft → SEC-Ω → package (always dry-run submit by default)
python scripts/run_automation.py --keyword "robotics" --index 0

# Live S2S only after certificate + explicit flag (see docs/ONBOARDING.md)
export AUTOGRANTED_S2S_LIVE=true
python scripts/run_automation.py --keyword "robotics" --live-submit
```

### One-time human setup

Real federal submission requires:

1. **SAM.gov UEI** (active entity registration)
2. **Grants.gov** org profile + **Expanded AOR** role
3. **Digital certificate** registered with Grants.gov for Applicant S2S V2.0

Full checklist and env vars: **[docs/ONBOARDING.md](docs/ONBOARDING.md)**

After onboarding, put non-secret org data in `~/.autogranted/org_profile.json` (see `profiles/org_profile.example.json`). Secrets stay in environment variables only — never in git.

### Architecture (automation path)

```
Grants.gov Search2 / XML extract
        │
        ▼  #opp-raw
┌───────────────────────┐
│  SignalMesh Hub       │  72-slot spatial grid
│  (SHA-256 % 72)       │
└───────────┬───────────┘
            │
    ┌───────┴──────────────┐
    ▼                      ▼
Profile hydrate      Ollama Cloud SLMs
    │                      │
    └──────────┬───────────┘
               ▼
         SEC-Ω Warden
               │
               ▼  #pkg-ready
    LaTeX / DOCX / Grant XML
               │
               ▼
    S2S SubmitApplication   ← gated: cert + AOR + AUTOGRANTED_S2S_LIVE
               │
               ▼  #submission-status
    Lifecycle Monitor + KPI telemetry
```

## Core modules

| Path | Responsibility |
|------|----------------|
| `engine.py` | SignalMesh, SEC-Ω, Grants.gov scout, compiler, monitor |
| `ollama_cloud.py` | Ollama Cloud client + grant-model ranking |
| `credentials/` | Org profile + secret vault (env only) |
| `s2s/` | Applicant S2S V2.0 client (dry-run by default) |
| `automation/` | End-to-end orchestrator |
| `pipeline/` | Gradio UI + FastAPI helpers |
| `app.py` | Thin entrypoint |

## Hugging Face Spaces

The same `app.py` is HF-Spaces ready. Set the Space to **Docker** or **Gradio** and point the entry to `app.py`.

## SignalMesh integration

AutoGrantED interoperates with the standalone SignalMesh runtime:

- https://github.com/Ig0tU/signalmesh  
- https://huggingface.co/spaces/acecalisto3/signalmesh  
- https://kyklos.io  

Agents subscribe to frequency bands (`#opp-raw`, `#grant-active`, `#draft-review`, `#pkg-ready`, …). Context is hydrated **before** inference.

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
