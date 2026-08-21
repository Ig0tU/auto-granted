"""
Full Automation Suite
=====================
Orchestrates:
  Scout → Match → Profile hydrate → SLM draft → SEC-Ω → Package → (optional) S2S submit → Track

Default stop point: "ready for AOR sign-off".
Live submit only when certificate + AUTOGRANTED_S2S_LIVE=true.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from credentials.vault import CredentialVault, OrgProfile
from s2s.client import GrantsGovS2SClient, S2SConfig, SubmissionResult


@dataclass
class PipelineResult:
    stage: str
    success: bool
    opportunity: Optional[Dict[str, Any]] = None
    draft_sections: Dict[str, str] = field(default_factory=dict)
    audit: Dict[str, Any] = field(default_factory=dict)
    package_paths: Dict[str, Optional[str]] = field(default_factory=dict)
    submission: Optional[SubmissionResult] = None
    messages: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "stage": self.stage,
            "success": self.success,
            "opportunity": self.opportunity,
            "draft_sections": self.draft_sections,
            "audit": self.audit,
            "package_paths": self.package_paths,
            "messages": self.messages,
            "timestamp": self.timestamp,
        }
        if self.submission:
            d["submission"] = {
                "success": self.submission.success,
                "tracking_number": self.submission.tracking_number,
                "message": self.submission.message,
                "dry_run": self.submission.dry_run,
                "package_hash": self.submission.package_hash,
                "environment": self.submission.environment,
            }
        return d


class AutomationSuite:
    """
    High-level controller. Reuses existing engine + ollama_cloud + pipeline helpers.
    """

    def __init__(
        self,
        vault: Optional[CredentialVault] = None,
        s2s: Optional[GrantsGovS2SClient] = None,
    ) -> None:
        self.vault = vault or CredentialVault()
        self.s2s = s2s or GrantsGovS2SClient(S2SConfig.from_env())
        self.export_dir = Path(os.environ.get(
            "AUTOGRANTED_EXPORT_DIR",
            str(Path(__file__).resolve().parent.parent / "exports"),
        ))
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def readiness(self) -> Dict[str, Any]:
        v = self.vault.status()
        s = self.s2s.status()
        return {
            "vault": v,
            "s2s": s,
            "next_human_step": self._next_human_step(v, s),
        }

    def _next_human_step(self, vault_status: Dict, s2s_status: Dict) -> str:
        if not vault_status.get("uei_present"):
            return "Register organization in SAM.gov and obtain UEI (see docs/ONBOARDING.md §1)"
        if not vault_status.get("aor_present"):
            return "Create Grants.gov profile and assign Expanded AOR (see docs/ONBOARDING.md §2)"
        if not s2s_status.get("cert_present"):
            return "Obtain & register digital certificate for S2S (see docs/ONBOARDING.md §3)"
        if not s2s_status.get("allow_live_submit"):
            return "Set AUTOGRANTED_S2S_LIVE=true only after final human review of a package"
        return "System ready for live S2S submit under AOR authority"

    def discover(self, keyword: str = "", rows: int = 25) -> List[Dict[str, Any]]:
        from engine import scout
        hits = scout.fetch(keywords=keyword or "artificial intelligence", rows=rows)
        if not hits:
            hits = scout.fallback_hits(keyword or "artificial intelligence")
        return hits

    def draft(
        self,
        opportunity: Dict[str, Any],
        *,
        ollama_key: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Dict[str, str]:
        """Generate proposal sections via Ollama Cloud."""
        import ollama_cloud

        key = ollama_key or self.vault.ollama_key
        if not key:
            title = opportunity.get("title") or opportunity.get("opportunityTitle") or "Untitled"
            agency = opportunity.get("agency") or opportunity.get("agencyName") or "NSF"
            return {
                "overview": f"[TEMPLATE] Overview for {title} ({agency}). Replace with SLM output.",
                "intellectual_merit": "[TEMPLATE] Intellectual merit placeholder.",
                "broader_impacts": "[TEMPLATE] Broader impacts placeholder.",
                "narrative": "[TEMPLATE] Project description narrative placeholder.",
                "dmp": "Data will be deposited in a FAIR-compliant public repository within 12 months of collection.",
            }

        client = ollama_cloud.OllamaCloudClient(api_key=key)
        return client.generate_proposal_sections(opportunity, model=model)

    def audit(self, opportunity: Dict[str, Any], sections: Dict[str, str]) -> Dict[str, Any]:
        from engine import SecOmegaEngine

        agency = (
            opportunity.get("agency")
            or opportunity.get("agencyName")
            or "NSF"
        )
        draft = {
            "agency": agency,
            "formatting": {
                "font_family": "Times New Roman",
                "font_size": 12.0 if "DARPA" in str(agency).upper() else 11.0,
                "margin_inches": 1.0,
            },
            "sections": {
                "project_summary": {
                    "overview": sections.get("overview", ""),
                    "intellectual_merit": sections.get("intellectual_merit", ""),
                    "broader_impacts": sections.get("broader_impacts", ""),
                },
                "project_description": {
                    "estimated_pages": 14,
                    "content": sections.get("narrative", ""),
                },
                "data_management_plan": sections.get("dmp", ""),
            },
        }
        return SecOmegaEngine.audit(draft)

    def package(
        self,
        opportunity: Dict[str, Any],
        sections: Dict[str, str],
        sub_id: Optional[str] = None,
    ) -> Dict[str, Optional[str]]:
        from engine import ProposalCompiler

        sub_id = sub_id or f"SUB-{int(time.time())}"
        title = (
            opportunity.get("title")
            or opportunity.get("opportunityTitle")
            or "Proposal"
        )
        manifest = {
            "compiled_artifacts": {
                "cover_sheet": {"proposal_title": title},
                "summary": {
                    "overview": sections.get("overview", ""),
                    "intellectual_merit": sections.get("intellectual_merit", ""),
                    "broader_impacts": sections.get("broader_impacts", ""),
                },
                "core_narrative": sections.get("narrative", ""),
                "data_management_plan": sections.get("dmp", ""),
            }
        }
        tex = ProposalCompiler.compile_latex(sub_id, manifest)
        docx = ProposalCompiler.compile_docx(sub_id, manifest)

        profile = self.vault.load_profile()
        xml_path = self.export_dir / f"{sub_id}.grantapp.xml"
        xml_body = self._build_stub_grant_xml(opportunity, sections, profile, sub_id)
        xml_path.write_text(xml_body, encoding="utf-8")

        return {
            "tex": os.path.abspath(tex) if tex else None,
            "docx": os.path.abspath(docx) if docx else None,
            "grant_xml": str(xml_path.resolve()),
            "sub_id": sub_id,
        }

    def _build_stub_grant_xml(
        self,
        opportunity: Dict[str, Any],
        sections: Dict[str, str],
        profile: OrgProfile,
        sub_id: str,
    ) -> str:
        opp_id = (
            opportunity.get("opportunityNumber")
            or opportunity.get("id")
            or opportunity.get("opportunity_id")
            or "UNKNOWN"
        )
        title = (
            opportunity.get("title")
            or opportunity.get("opportunityTitle")
            or "Untitled"
        )

        def esc(s: str) -> str:
            return (
                (s or "")
                .replace("&", "&")
                .replace("<", "<")
                .replace(">", ">")
                .replace('"', """)
            )

        return f"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<!-- AutoGrantED package stub – replace with opportunity-specific schema before live S2S -->
<GrantApplication>
  <PackageInfo>
    <SubmissionID>{esc(sub_id)}</SubmissionID>
    <OpportunityID>{esc(str(opp_id))}</OpportunityID>
    <OpportunityTitle>{esc(str(title))}</OpportunityTitle>
  </PackageInfo>
  <Applicant>
    <LegalName>{esc(profile.legal_name)}</LegalName>
    <UEI>{esc(profile.uei)}</UEI>
    <AORName>{esc(profile.aor_name)}</AORName>
    <AOREmail>{esc(profile.aor_email)}</AOREmail>
  </Applicant>
  <ProjectSummary>
    <Overview>{esc(sections.get("overview", ""))}</Overview>
    <IntellectualMerit>{esc(sections.get("intellectual_merit", ""))}</IntellectualMerit>
    <BroaderImpacts>{esc(sections.get("broader_impacts", ""))}</BroaderImpacts>
  </ProjectSummary>
  <ProjectDescription>{esc(sections.get("narrative", ""))}</ProjectDescription>
  <DataManagementPlan>{esc(sections.get("dmp", ""))}</DataManagementPlan>
</GrantApplication>
"""

    def submit_package(
        self,
        grant_xml_path: str,
        *,
        force_dry_run: bool = True,
    ) -> SubmissionResult:
        path = Path(grant_xml_path)
        if not path.is_file():
            return SubmissionResult(
                success=False,
                message=f"Package not found: {grant_xml_path}",
                dry_run=True,
            )
        xml = path.read_text(encoding="utf-8")
        return self.s2s.submit_application(xml, force_dry_run=force_dry_run)

    def run(
        self,
        keyword: str = "artificial intelligence",
        *,
        opportunity_index: int = 0,
        ollama_key: Optional[str] = None,
        model: Optional[str] = None,
        live_submit: bool = False,
    ) -> PipelineResult:
        messages: List[str] = []
        messages.append(f"Readiness: {json.dumps(self.readiness(), indent=2)}")

        opps = self.discover(keyword=keyword, rows=10)
        if not opps:
            return PipelineResult(
                stage="discover",
                success=False,
                messages=["No opportunities returned from Grants.gov scout."],
            )
        idx = min(max(0, opportunity_index), len(opps) - 1)
        opp = opps[idx]
        messages.append(f"Selected opportunity [{idx}]: {opp.get('title') or opp.get('opportunityTitle')}")

        sections = self.draft(opp, ollama_key=ollama_key, model=model)
        messages.append("Draft sections generated.")

        audit = self.audit(opp, sections)
        if not audit.get("is_valid", False):
            return PipelineResult(
                stage="sec_omega",
                success=False,
                opportunity=opp,
                draft_sections=sections,
                audit=audit,
                messages=messages + ["SEC-Ω rejected package."] + audit.get("errors", []),
            )
        messages.append("SEC-Ω passed.")

        paths = self.package(opp, sections)
        messages.append(f"Artifacts: {paths}")

        force_dry = not live_submit
        sub = self.submit_package(paths["grant_xml"], force_dry_run=force_dry)
        messages.append(sub.message)

        return PipelineResult(
            stage="complete",
            success=sub.success or sub.dry_run,
            opportunity=opp,
            draft_sections=sections,
            audit=audit,
            package_paths=paths,
            submission=sub,
            messages=messages,
        )
