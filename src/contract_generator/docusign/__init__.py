"""Send generated contract PDFs to DocuSign for signature (JWT Grant, tab auto-detection)."""

from contract_generator.docusign.client import DocuSignClient
from contract_generator.docusign.config import DocuSignConfig
from contract_generator.docusign.envelope_factory import EnvelopeFactory
from contract_generator.docusign.errors import DocuSignError
from contract_generator.docusign.esign_client import EsignDocuSignClient
from contract_generator.docusign.jwt_authenticator import JwtAuthenticator
from contract_generator.docusign.send_request import SendRequest, Signer
from contract_generator.docusign.sender import DocuSignSender

__all__ = [
    "DocuSignClient",
    "DocuSignConfig",
    "DocuSignError",
    "DocuSignSender",
    "EnvelopeFactory",
    "EsignDocuSignClient",
    "JwtAuthenticator",
    "SendRequest",
    "Signer",
]
