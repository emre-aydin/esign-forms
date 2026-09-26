from __future__ import annotations

from contract_generator.docusign.client import DocuSignClient
from contract_generator.docusign.config import DocuSignConfig
from contract_generator.docusign.envelope_factory import EnvelopeFactory
from contract_generator.docusign.esign_client import EsignDocuSignClient
from contract_generator.docusign.send_request import SendRequest


class DocuSignSender:
    """Facade: builds the envelope for a :class:`SendRequest` and sends it; returns its id."""

    def __init__(self, envelope_factory: EnvelopeFactory, client: DocuSignClient) -> None:
        self._envelope_factory = envelope_factory
        self._client = client

    @staticmethod
    def for_live_docusign(config: DocuSignConfig) -> DocuSignSender:
        return DocuSignSender(EnvelopeFactory(), EsignDocuSignClient(config))

    def send_for_signature(self, request: SendRequest) -> str:
        return self._client.create_envelope(self._envelope_factory.build(request))
