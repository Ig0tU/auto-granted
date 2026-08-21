# AutoGrantED — One-Time Human Onboarding

This is the **only** required human setup for the full automation suite.
After these steps, discovery → draft → compliance → package → status tracking
can run with minimal involvement. Live submission still requires an explicit
AOR authorization step (legal requirement).

---

## §1 — SAM.gov Unique Entity Identifier (UEI)

1. Create a Login.gov account (if you do not have one).
2. Go to [https://sam.gov](https://sam.gov) → Entity Registration.
3. Choose the registration purpose that matches you:
   - **Federal Financial Assistance Only** (grants), or
   - **All Awards** (grants + contracts).
4. Complete entity validation (legal name, physical address, TIN/EIN).
5. Receive your **12-character UEI**.
6. Wait until registration status is **Active** (often 7–10 business days).

Record:
```
UEI: ____________________
Legal Name: ____________________
EBiz POC email: ____________________
```

There is **no fee**. Keep the registration current (annual renewal).

---

## §2 — Grants.gov Organization Profile + Expanded AOR

1. Go to [https://grants.gov](https://grants.gov) and create an account using the
   **same email** as the SAM.gov EBiz POC when possible.
2. Add an organization profile using the UEI from §1.
3. The EBiz POC must log in and assign roles:
   - At least one user must receive the **Standard AOR** or **Expanded AOR** role.
   - Expanded AOR is required for System-to-System (S2S) certificate authorization.
4. Confirm you can see Workspace and can start an application for a test opportunity
   in the Grants.gov training environment if desired.

Record:
```
AOR Name: ____________________
AOR Email: ____________________
AOR Title: ____________________
```

---

## §3 — Digital Certificate for Applicant S2S

Programmatic submission uses **Applicant System-to-System V2.0** (SOAP + mutual TLS).

1. Obtain a digital certificate from a recognized CA (or your institution’s PKI).
   Common options: commercial SSL/TLS client certs accepted by Grants.gov.
2. Follow the current Grants.gov **Applicant Certificates** instructions:
   - https://www.grants.gov/system-to-system/applicant-system-to-system
3. Submit the certificate to Grants.gov for installation (process documented on
   the Applicant S2S pages; historically a PDF request to the Grants.gov PMO).
4. After Grants.gov confirms installation, the **EBiz POC / Expanded AOR**
   authorizes the certificate in the Grants.gov UI.
5. Store the certificate file and private key **outside the git repo**.

Environment variables (never commit values):

```bash
export AUTOGRANTED_S2S_CERT_PATH="/secure/path/client.pem"
export AUTOGRANTED_S2S_KEY_PATH="/secure/path/client.key"   # if separate
export AUTOGRANTED_S2S_CERT_PASS="..."                      # if encrypted
export AUTOGRANTED_S2S_ENV="training"                       # or "production"
# Only after human review of a real package:
export AUTOGRANTED_S2S_LIVE="true"
```

Test first against the **training** endpoint:
`https://trainingws.grants.gov/grantsws-applicant/services/v2/ApplicantWebServicesSoapPort`

---

## §4 — Organization Profile File (non-secret)

Create `~/.autogranted/org_profile.json` (or set `AUTOGRANTED_PROFILE_DIR`):

```json
{
  "legal_name": "Example Research Institute",
  "uei": "XXXXXXXXXXXX",
  "cage_code": "",
  "ein_last4": "1234",
  "address_line1": "123 Science Way",
  "address_city": "Cambridge",
  "address_state": "MA",
  "address_zip": "02139",
  "address_country": "USA",
  "ebiz_poc_email": "ebiz@example.edu",
  "aor_name": "Jane Doe",
  "aor_email": "jane.doe@example.edu",
  "aor_title": "Authorized Organizational Representative",
  "institution_type": "University",
  "naics_codes": ["541715"],
  "research_areas": ["artificial intelligence", "robotics"],
  "facilities_summary": "Shared compute cluster, wet lab wing A.",
  "prior_awards_summary": "NSF CAREER 2022; DARPA YFA 2024.",
  "default_budget_indirect_rate": 0.55,
  "notes": ""
}
```

Or use the Python helper:

```python
from credentials import CredentialVault, OrgProfile
v = CredentialVault()
p = OrgProfile(legal_name="...", uei="...", aor_name="...", aor_email="...")
v.save_profile(p)
print(v.status())
```

---

## §5 — Optional: Ollama Cloud Key

For real SLM drafting (not templates):

1. Visit https://ollama.com/settings/keys
2. Create an API key
3. Either paste it in the Gradio UI or:

```bash
export AUTOGRANTED_OLLAMA_KEY="your_key_here"
```

---

## §6 — What the automation will never do

- Invent a UEI or certificate
- Submit without an Expanded AOR–authorized certificate
- Bypass the legal certification that the application content is true
- Store secrets inside the git repository

Live `SubmitApplication` is gated behind `AUTOGRANTED_S2S_LIVE=true` **and**
a present certificate file. Default mode is always dry-run / package-only.

---

## Quick readiness check

```bash
cd auto-granted
python -c "
from automation import AutomationSuite
import json
print(json.dumps(AutomationSuite().readiness(), indent=2))
"
```

Follow the `next_human_step` field until it reports ready for live S2S.
