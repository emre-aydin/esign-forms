from __future__ import annotations

from docusign_esign import EnvelopeDefinition, EnvelopesApi
from docusign_esign.client.api_exception import ApiException
from urllib3.exceptions import HTTPError

from esign_forms.docusign.config import DocuSignConfig
from esign_forms.docusign.errors import DocuSignError
from esign_forms.docusign.jwt_authenticator import JwtAuthenticator


class EsignDocuSignClient:
    """:class:`DocuSignClient` backed by the official SDK (network I/O)."""

    def __init__(self, config: DocuSignConfig) -> None:
        self._config = config
        self._authenticator = JwtAuthenticator(config)

    def create_envelope(self, envelope: EnvelopeDefinition) -> str:
        api_client = self._authenticator.authenticate()
        try:
            summary = EnvelopesApi(api_client).create_envelope(
                self._config.account_id, envelope_definition=envelope
            )
        except ApiException as e:
            body = e.body.decode("utf-8", "replace") if isinstance(e.body, bytes) else e.body
            raise DocuSignError(f"Failed to create DocuSign envelope: {body}") from e
        except (HTTPError, OSError) as e:
            raise DocuSignError("Failed to create DocuSign envelope") from e
        return str(summary.envelope_id)
