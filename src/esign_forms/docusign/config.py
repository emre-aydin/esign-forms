from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from esign_forms.docusign._validation import require_text


@dataclass(frozen=True)
class DocuSignConfig:
    """Credentials and endpoints for JWT Grant authentication.

    :param account_id: DocuSign account id (GUID)
    :param oauth_base_path: OAuth host, e.g. ``account-d.docusign.com`` (demo) or
        ``account.docusign.com`` (production)
    :param integration_key: JWT integration key (OAuth client id)
    :param user_id: GUID of the impersonated user (must have granted consent)
    :param private_key: RSA private key PEM bytes registered for the integration key
    """

    account_id: str
    oauth_base_path: str
    integration_key: str
    user_id: str
    private_key: bytes = field(repr=False)

    def __post_init__(self) -> None:
        require_text(self.account_id, "account_id")
        require_text(self.oauth_base_path, "oauth_base_path")
        require_text(self.integration_key, "integration_key")
        require_text(self.user_id, "user_id")
        if not self.private_key:
            raise ValueError("private_key must not be empty")

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> DocuSignConfig:
        """Builds the config from ``DOCUSIGN_*`` environment variables.

        Reads ``DOCUSIGN_ACCOUNT_ID``, ``DOCUSIGN_OAUTH_BASE_PATH``, ``DOCUSIGN_INTEGRATION_KEY``,
        ``DOCUSIGN_USER_ID``, and the key from ``DOCUSIGN_PRIVATE_KEY`` (inline PEM, preferred) or
        ``DOCUSIGN_PRIVATE_KEY_PATH``. Raises ``ValueError`` if anything is missing.
        """
        env = os.environ if env is None else env
        return cls(
            account_id=env.get("DOCUSIGN_ACCOUNT_ID", ""),
            oauth_base_path=env.get("DOCUSIGN_OAUTH_BASE_PATH", ""),
            integration_key=env.get("DOCUSIGN_INTEGRATION_KEY", ""),
            user_id=env.get("DOCUSIGN_USER_ID", ""),
            private_key=_private_key_from_env(env),
        )


def _private_key_from_env(env: Mapping[str, str]) -> bytes:
    inline = env.get("DOCUSIGN_PRIVATE_KEY")
    if inline and inline.strip():
        return inline.encode("utf-8")
    path = env.get("DOCUSIGN_PRIVATE_KEY_PATH")
    if path and path.strip():
        try:
            return Path(path).read_bytes()
        except OSError as e:
            raise ValueError(f"Failed to read DOCUSIGN_PRIVATE_KEY_PATH: {path}") from e
    raise ValueError("DOCUSIGN_PRIVATE_KEY or DOCUSIGN_PRIVATE_KEY_PATH must be set")
