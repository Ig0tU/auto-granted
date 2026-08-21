"""
Grants.gov Applicant System-to-System (S2S) V2.0 client
======================================================
Official path for programmatic submission.

Endpoints (from Grants.gov docs):
  Training : https://trainingws.grants.gov/grantsws-applicant/services/v2/ApplicantWebServicesSoapPort
  Production: https://ws07.grants.gov/grantsws-applicant/services/v2/ApplicantWebServicesSoapPort

Requires:
  - Active SAM.gov UEI + Grants.gov org profile
  - Expanded AOR role
  - Digital certificate registered with Grants.gov (mutual TLS)
  - Well-formed GrantApplication XML matching the opportunity package schema

This client is intentionally conservative:
  - Default mode is dry-run / package-only
  - Real SubmitApplication only fires when explicitly enabled AND certificate is present
  - Never fabricates credentials or bypasses AOR certification
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("autogranted.s2s")

TRAINING_ENDPOINT = (
    "https://trainingws.grants.gov/grantsws-applicant/services/v2/ApplicantWebServicesSoapPort"
)
PRODUCTION_ENDPOINT = (
    "https://ws07.grants.gov/grantsws-applicant/services/v2/ApplicantWebServicesSoapPort"
)


@dataclass
class S2SConfig:
    environment: str = "training"          # "training" | "production"
    cert_path: Optional[str] = None
    key_path: Optional[str] = None
    cert_passphrase: Optional[str] = None
    allow_live_submit: bool = False        # must be True + cert present to actually submit

    @property
    def endpoint(self) -> str:
        if self.environment == "production":
            return PRODUCTION_ENDPOINT
        return TRAINING_ENDPOINT

    @classmethod
    def from_env(cls) -> "S2SConfig":
        return cls(
            environment=os.environ.get("AUTOGRANTED_S2S_ENV", "training"),
            cert_path=os.environ.get("AUTOGRANTED_S2S_CERT_PATH"),
            key_path=os.environ.get("AUTOGRANTED_S2S_KEY_PATH"),
            cert_passphrase=os.environ.get("AUTOGRANTED_S2S_CERT_PASS"),
            allow_live_submit=os.environ.get("AUTOGRANTED_S2S_LIVE", "").lower() in ("1", "true", "yes"),
        )


@dataclass
class SubmissionResult:
    success: bool
    tracking_number: Optional[str] = None
    message: str = ""
    environment: str = "training"
    dry_run: bool = True
    raw: Dict[str, Any] = field(default_factory=dict)
    package_hash: Optional[str] = None
    timestamp: float = field(default_factory=time.time)


class GrantsGovS2SClient:
    """
    Thin wrapper around Applicant Web Services V2.0.

    Full SOAP/MTOM implementation requires zeep + requests + the registered
    client certificate. Until the certificate is present this client stays
    in package-validation / dry-run mode so the rest of the automation suite
    can be developed and tested safely.
    """

    def __init__(self, config: Optional[S2SConfig] = None) -> None:
        self.config = config or S2SConfig.from_env()
        self._zeep_client = None

    def is_cert_present(self) -> bool:
        return bool(self.config.cert_path and Path(self.config.cert_path).is_file())

    def can_live_submit(self) -> bool:
        return (
            self.config.allow_live_submit
            and self.is_cert_present()
            and self.config.environment in ("training", "production")
        )

    def status(self) -> Dict[str, Any]:
        return {
            "environment": self.config.environment,
            "endpoint": self.config.endpoint,
            "cert_present": self.is_cert_present(),
            "allow_live_submit": self.config.allow_live_submit,
            "can_live_submit": self.can_live_submit(),
            "mode": "live" if self.can_live_submit() else "dry-run / package-only",
        }

    @staticmethod
    def hash_package(xml_bytes: bytes) -> str:
        return hashlib.sha256(xml_bytes).hexdigest()

    def validate_application_xml(self, xml: str | bytes) -> Dict[str, Any]:
        """Basic structural checks before any network call."""
        raw = xml.encode("utf-8") if isinstance(xml, str) else xml
        text = raw.decode("utf-8", errors="replace")
        checks = {
            "non_empty": len(raw) > 100,
            "has_grant_application_root": "GrantApplication" in text or "grantApplication" in text,
            "has_opportunity_id_hint": any(
                k in text for k in ("OpportunityID", "opportunityID", "FundingOpportunityNumber")
            ),
            "size_bytes": len(raw),
            "sha256": self.hash_package(raw),
        }
        checks["ok"] = checks["non_empty"] and checks["has_grant_application_root"]
        return checks

    def _build_zeep_client(self):
        if self._zeep_client is not None:
            return self._zeep_client
        if not self.is_cert_present():
            raise RuntimeError(
                "S2S certificate not configured. Set AUTOGRANTED_S2S_CERT_PATH "
                "and complete the one-time Grants.gov certificate registration "
                "(see docs/ONBOARDING.md)."
            )
        try:
            from requests import Session
            from zeep import Client
            from zeep.transports import Transport
        except ImportError as e:
            raise RuntimeError(
                "zeep and requests are required for live S2S. "
                "pip install zeep requests"
            ) from e

        session = Session()
        cert = self.config.cert_path
        if self.config.key_path:
            cert = (self.config.cert_path, self.config.key_path)
        session.cert = cert

        wsdl = self.config.endpoint + "?wsdl"
        transport = Transport(session=session, timeout=120)
        self._zeep_client = Client(wsdl=wsdl, transport=transport)
        return self._zeep_client

    def submit_application(
        self,
        grant_application_xml: str | bytes,
        attachments: Optional[List[Dict[str, Any]]] = None,
        *,
        force_dry_run: bool = False,
    ) -> SubmissionResult:
        validation = self.validate_application_xml(grant_application_xml)
        package_hash = validation["sha256"]

        if force_dry_run or not self.can_live_submit():
            msg = (
                "DRY-RUN: package validated locally. "
                "Live SubmitApplication requires certificate + AUTOGRANTED_S2S_LIVE=true "
                "and Expanded AOR authorization. See docs/ONBOARDING.md."
            )
            if not validation["ok"]:
                msg = "DRY-RUN FAILED validation: " + str(validation)
            return SubmissionResult(
                success=validation["ok"],
                tracking_number=None,
                message=msg,
                environment=self.config.environment,
                dry_run=True,
                raw={"validation": validation},
                package_hash=package_hash,
            )

        try:
            client = self._build_zeep_client()
            raw_xml = (
                grant_application_xml
                if isinstance(grant_application_xml, str)
                else grant_application_xml.decode("utf-8")
            )
            response = client.service.SubmitApplication(
                GrantApplicationXML=raw_xml,
            )
            tracking = None
            if hasattr(response, "GrantsGovTrackingNumber"):
                tracking = str(response.GrantsGovTrackingNumber)
            elif isinstance(response, dict):
                tracking = response.get("GrantsGovTrackingNumber")

            return SubmissionResult(
                success=True,
                tracking_number=tracking,
                message="Submitted via S2S V2.0",
                environment=self.config.environment,
                dry_run=False,
                raw={"response": str(response)},
                package_hash=package_hash,
            )
        except Exception as exc:
            logger.exception("S2S SubmitApplication failed")
            return SubmissionResult(
                success=False,
                tracking_number=None,
                message=f"S2S submit error: {exc}",
                environment=self.config.environment,
                dry_run=False,
                raw={"error": str(exc)},
                package_hash=package_hash,
            )

    def get_submission_list(self) -> Dict[str, Any]:
        if not self.can_live_submit():
            return {
                "ok": False,
                "message": "Live S2S not configured; cannot list submissions.",
                "items": [],
            }
        try:
            client = self._build_zeep_client()
            response = client.service.GetSubmissionList()
            return {"ok": True, "items": response}
        except Exception as exc:
            return {"ok": False, "message": str(exc), "items": []}
