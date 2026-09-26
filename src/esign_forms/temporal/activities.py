from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from pathlib import Path

from temporalio import activity

from esign_forms.docusign.config import DocuSignConfig
from esign_forms.docusign.send_request import SendRequest, Signer
from esign_forms.docusign.sender import DocuSignSender
from esign_forms.generator import FormGenerator
from esign_forms.model import FormData
from esign_forms.temporal.dto import FormSigningRequest


class FormActivities:
    """Activities of the signing workflow. Methods are synchronous; run them in a thread pool.

    DocuSign credentials come from ``DOCUSIGN_*`` environment variables at send time
    (``DOCUSIGN_PRIVATE_KEY`` inline PEM, or ``DOCUSIGN_PRIVATE_KEY_PATH``).
    """

    def __init__(
        self,
        generator: FormGenerator | None = None,
        env: Mapping[str, str] | None = None,
        sender_factory: Callable[
            [DocuSignConfig], DocuSignSender
        ] = DocuSignSender.for_live_docusign,
    ) -> None:
        self._generator = generator or FormGenerator()
        self._env = os.environ if env is None else env
        self._sender_factory = sender_factory

    @activity.defn(name="generate_pdf")
    def generate_pdf(self, request: FormSigningRequest) -> bytes:
        return self._generator.generate(
            Path(request.template_path),
            FormData(request.parameters),
            request.expected_field_names,
            request.required_field_names,
        )

    @activity.defn(name="send_to_docusign")
    def send_to_docusign(self, pdf: bytes, request: FormSigningRequest) -> str:
        config = DocuSignConfig.from_env(self._env)
        signers = [Signer(s.name, s.email, s.routing_order) for s in request.signers]
        send_request = SendRequest(request.document_name, pdf, request.email_subject, signers)
        return self._sender_factory(config).send_for_signature(send_request)
