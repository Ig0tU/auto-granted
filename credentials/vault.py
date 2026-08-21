"""
Credential Vault
================
One-time human onboarding stores:
  - SAM.gov UEI
  - Grants.gov org profile metadata
  - Path to digital certificate (mutual TLS for S2S)
  - Optional Ollama Cloud key (also accepted at runtime)

Nothing in this module ever writes secrets into the git-tracked tree.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional


# Default locations (outside repo when possible)
DEFAULT_PROFILE_DIR = Path(os.environ.get(
    "AUTOGRANTED_PROFILE_DIR",
    str(Path.home() / ".autogranted"),
))
DEFAULT_PROFILE_FILE = DEFAULT_PROFILE_DIR / "org_profile.json"


@dataclass
class OrgProfile:
    """Non-secret organizational identity used for form filling & matching."""

    legal_name: str = ""
    uei: str = ""                          # Unique Entity Identifier (SAM.gov)
    cage_code: str = ""
    ein_last4: str = ""                    # never store full EIN
    address_line1: str = ""
    address_city: str = ""
    address_state: str = ""
    address_zip: str = ""
    address_country: str = "USA"
    ebiz_poc_email: str = ""
    aor_name: str = ""
    aor_email: str = ""
    aor_title: str = ""
    institution_type: str = ""             # e.g. "Nonprofit", "University", "Small Business"
    naics_codes: list = field(default_factory=list)
    research_areas: list = field(default_factory=list)
    facilities_summary: str = ""
    prior_awards_summary: str = ""
    default_budget_indirect_rate: float = 0.0
    notes: str = ""

    def is_ready_for_forms(self) -> bool:
        return bool(self.legal_name and self.uei and self.aor_name and self.aor_email)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OrgProfile":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


class CredentialVault:
    """
    Runtime access to credentials.

    Secrets (never persisted by this class into the repo):
      AUTOGRANTED_S2S_CERT_PATH   – path to client certificate (.p12 / .pem)
      AUTOGRANTED_S2S_KEY_PATH    – path to private key if separate
      AUTOGRANTED_S2S_CERT_PASS   – passphrase for the certificate
      AUTOGRANTED_OLLAMA_KEY      – Ollama Cloud bearer token
      AUTOGRANTED_GRANTS_API_KEY  – optional Grants.gov REST key (if issued)

    Profile (non-secret) lives in ~/.autogranted/org_profile.json by default.
    """

    def __init__(self, profile_path: Optional[Path] = None) -> None:
        self.profile_path = Path(profile_path) if profile_path else DEFAULT_PROFILE_FILE
        self._profile: Optional[OrgProfile] = None

    # ----- profile (non-secret) -----

    def load_profile(self) -> OrgProfile:
        if self._profile is not None:
            return self._profile
        if self.profile_path.is_file():
            data = json.loads(self.profile_path.read_text(encoding="utf-8"))
            self._profile = OrgProfile.from_dict(data)
        else:
            self._profile = OrgProfile()
        return self._profile

    def save_profile(self, profile: Optional[OrgProfile] = None) -> Path:
        p = profile or self._profile or OrgProfile()
        self.profile_path.parent.mkdir(parents=True, exist_ok=True)
        self.profile_path.write_text(
            json.dumps(p.to_dict(), indent=2),
            encoding="utf-8",
        )
        self._profile = p
        return self.profile_path

    # ----- secrets (env only) -----

    @property
    def s2s_cert_path(self) -> Optional[str]:
        return os.environ.get("AUTOGRANTED_S2S_CERT_PATH") or None

    @property
    def s2s_key_path(self) -> Optional[str]:
        return os.environ.get("AUTOGRANTED_S2S_KEY_PATH") or None

    @property
    def s2s_cert_pass(self) -> Optional[str]:
        return os.environ.get("AUTOGRANTED_S2S_CERT_PASS") or None

    @property
    def ollama_key(self) -> Optional[str]:
        return os.environ.get("AUTOGRANTED_OLLAMA_KEY") or os.environ.get("OLLAMA_API_KEY") or None

    @property
    def grants_api_key(self) -> Optional[str]:
        return os.environ.get("AUTOGRANTED_GRANTS_API_KEY") or None

    def s2s_ready(self) -> bool:
        """True only when mutual-TLS material is present for production submit."""
        cert = self.s2s_cert_path
        return bool(cert and Path(cert).is_file())

    def status(self) -> Dict[str, Any]:
        profile = self.load_profile()
        return {
            "profile_path": str(self.profile_path),
            "profile_ready_for_forms": profile.is_ready_for_forms(),
            "uei_present": bool(profile.uei),
            "aor_present": bool(profile.aor_name and profile.aor_email),
            "s2s_cert_configured": self.s2s_ready(),
            "ollama_key_present": bool(self.ollama_key),
            "grants_api_key_present": bool(self.grants_api_key),
            "can_draft": True,
            "can_package": profile.is_ready_for_forms(),
            "can_submit_s2s": self.s2s_ready() and profile.is_ready_for_forms(),
        }


def load_org_profile(path: Optional[str] = None) -> OrgProfile:
    vault = CredentialVault(Path(path) if path else None)
    return vault.load_profile()
