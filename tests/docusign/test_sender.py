from docusign_esign import EnvelopeDefinition

from esign_forms.docusign import DocuSignSender, EnvelopeFactory, SendRequest, Signer

FAKE_PDF = b"%PDF-1.4 fake contract bytes"


class FakeClient:
    def __init__(self, envelope_id: str) -> None:
        self.envelope_id = envelope_id
        self.captured: EnvelopeDefinition | None = None

    def create_envelope(self, envelope: EnvelopeDefinition) -> str:
        self.captured = envelope
        return self.envelope_id


def test_builds_envelope_and_delegates_to_client_returning_envelope_id() -> None:
    client = FakeClient("envelope-123")
    sender = DocuSignSender(EnvelopeFactory(), client)
    request = SendRequest(
        "Consulting Agreement", FAKE_PDF, "Please sign", [Signer("Jane Doe", "jane@example.com")]
    )
    assert sender.send_for_signature(request) == "envelope-123"
    assert client.captured is not None, "the client should receive the built envelope"
    assert client.captured.status == "sent"
    assert len(client.captured.documents) == 1


def test_uses_same_envelope_factory_output_passed_through() -> None:
    request = SendRequest("Agreement", FAKE_PDF, "Please sign", [Signer("Alice", "a@example.com")])
    expected = EnvelopeFactory().build(request)
    client = FakeClient("envelope-456")
    assert DocuSignSender(EnvelopeFactory(), client).send_for_signature(request) == "envelope-456"
    assert client.captured is not None
    assert client.captured.email_subject == expected.email_subject
    assert client.captured.documents[0].document_base64 == expected.documents[0].document_base64
