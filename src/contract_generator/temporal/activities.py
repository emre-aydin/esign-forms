from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from pathlib import Path

from temporalio import activity

from contract_generator.docusign.config import DocuSignConfig
from contract_generator.docusign.send_request import SendRequest, Signer
from contract_generator.docusign.sender import DocuSignSender
from contract_generator.generator import ContractGenerator
from contract_generator.model import ContractData
from contract_generator.temporal.dto import ContractSigningRequest


class ContractActivities:
    """Activities of the signing workflow. Methods are synchronous; run them in a thread pool.

    DocuSign credentials come from ``DOCUSIGN_*`` environment variables at send time
    (``DOCUSIGN_PRIVATE_KEY`` inline PEM, or ``DOCUSIGN_PRIVATE_KEY_PATH``).
    """

    def __init__(
        self,
        generator: ContractGenerator | None = None,
        env: Mapping[str, str] | None = None,
        sender_factory: Callable[
            [DocuSignConfig], DocuSignSender
        ] = DocuSignSender.for_live_docusign,
    ) -> None:
        self._generator = generator or ContractGenerator()
        self._env = os.environ if env is None else env
        self._sender_factory = sender_factory

    @activity.defn(name="generate_pdf")
    def generate_pdf(self, request: ContractSigningRequest) -> bytes:
        return self._generator.generate(
            request.template_name,
            ContractData(request.parameters),
            request.expected_field_names,
            request.required_field_names,
        )

    @activity.defn(name="send_to_docusign")
    def send_to_docusign(self, pdf: bytes, request: ContractSigningRequest) -> str:
        config = self._docusign_config_from_env()
        signers = [Signer(s.name, s.email, s.routing_order) for s in request.signers]
        send_request = SendRequest(request.document_name, pdf, request.email_subject, signers)
        return self._sender_factory(config).send_for_signature(send_request)

    def _docusign_config_from_env(self) -> DocuSignConfig:
        return DocuSignConfig(
            account_id=self._env.get("DOCUSIGN_ACCOUNT_ID", ""),
            oauth_base_path=self._env.get("DOCUSIGN_OAUTH_BASE_PATH", ""),
            integration_key=self._env.get("DOCUSIGN_INTEGRATION_KEY", ""),
            user_id=self._env.get("DOCUSIGN_USER_ID", ""),
            private_key=self._private_key_bytes(),
        )

    def _private_key_bytes(self) -> bytes:
        inline = self._env.get("DOCUSIGN_PRIVATE_KEY")
        if inline and inline.strip():
            return inline.encode("utf-8")
        path = self._env.get("DOCUSIGN_PRIVATE_KEY_PATH")
        if path and path.strip():
            try:
                return Path(path).read_bytes()
            except OSError as e:
                raise RuntimeError(f"Failed to read DOCUSIGN_PRIVATE_KEY_PATH: {path}") from e
        raise RuntimeError("DOCUSIGN_PRIVATE_KEY or DOCUSIGN_PRIVATE_KEY_PATH must be set")
