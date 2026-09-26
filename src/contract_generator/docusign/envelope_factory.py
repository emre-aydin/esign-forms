from __future__ import annotations

import base64

from docusign_esign import Document, EnvelopeDefinition, Recipients
from docusign_esign import Signer as DocuSignSigner

from contract_generator.docusign.send_request import SendRequest, Signer


class EnvelopeFactory:
    """Builds the SDK :class:`EnvelopeDefinition` for a :class:`SendRequest` (pure, no I/O).

    The document is sent with ``transform_pdf_fields="true"`` so DocuSign auto-converts the
    PDF's AcroForm fields into tabs (including ``DocusignSignHere*`` signature fields); no manual
    tab placement is needed. Required AcroForm fields become required tabs.
    """

    def build(self, request: SendRequest) -> EnvelopeDefinition:
        document = Document(
            document_base64=base64.b64encode(request.pdf_bytes).decode("ascii"),
            name=request.document_name,
            file_extension="pdf",
            document_id="1",
            transform_pdf_fields="true",
            # Converted tabs are all assigned to a single recipient; default to the first
            # signer, which is the supported single-signer path.
            assign_tabs_to_recipient_id="1",
        )
        signers = [
            self._to_docusign_signer(signer, recipient_id)
            for recipient_id, signer in enumerate(request.signers, start=1)
        ]
        return EnvelopeDefinition(
            email_subject=request.email_subject,
            documents=[document],
            recipients=Recipients(signers=signers),
            status="sent",
        )

    @staticmethod
    def _to_docusign_signer(signer: Signer, recipient_id: int) -> DocuSignSigner:
        return DocuSignSigner(
            name=signer.name,
            email=signer.email,
            recipient_id=str(recipient_id),
            routing_order=str(signer.routing_order),
        )
