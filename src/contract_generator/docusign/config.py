from __future__ import annotations

from dataclasses import dataclass, field

from contract_generator.docusign._validation import require_text


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
