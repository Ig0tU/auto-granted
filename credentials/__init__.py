"""Credential vault for AutoGrantED automation suite.

Never commit real secrets. All sensitive values come from environment
variables or an optional encrypted local store outside the git tree.
"""

from .vault import CredentialVault, OrgProfile, load_org_profile

__all__ = ["CredentialVault", "OrgProfile", "load_org_profile"]
