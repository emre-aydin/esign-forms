import base64

from esign_forms.docusign import EnvelopeFactory, SendRequest, Signer

FAKE_PDF = b"%PDF-1.4 fake contract bytes"


def test_builds_envelope_with_transform_pdf_fields_and_single_signer() -> None:
    request = SendRequest(
        "Consulting Agreement",
        FAKE_PDF,
        "Please sign: Consulting Agreement",
        [Signer("Jane Doe", "jane@example.com")],
    )
    envelope = EnvelopeFactory().build(request)

    assert envelope.status == "sent"
    assert envelope.email_subject == "Please sign: Consulting Agreement"
    assert len(envelope.documents) == 1
    document = envelope.documents[0]
    assert document.name == "Consulting Agreement"
    assert document.file_extension == "pdf"
    assert document.document_id == "1"
    assert document.transform_pdf_fields == "true"
    assert document.assign_tabs_to_recipient_id == "1"
    assert document.document_base64 == base64.b64encode(FAKE_PDF).decode()

    signers = envelope.recipients.signers
    assert len(signers) == 1
    assert signers[0].name == "Jane Doe"
    assert signers[0].email == "jane@example.com"
    assert signers[0].recipient_id == "1"
    assert signers[0].routing_order == "1"


def test_assigns_distinct_recipient_ids_for_multiple_signers() -> None:
    request = SendRequest(
        "Agreement",
        FAKE_PDF,
        "Please sign",
        [Signer("Alice", "alice@example.com", 1), Signer("Bob", "bob@example.com", 2)],
    )
    signers = EnvelopeFactory().build(request).recipients.signers
    assert [s.recipient_id for s in signers] == ["1", "2"]
    assert [s.routing_order for s in signers] == ["1", "2"]
