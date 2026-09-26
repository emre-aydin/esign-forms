from __future__ import annotations

import base64
import json

import pytest

from esign_forms.docusign.webhook import ConnectWebhookParser, WebhookParseError
from tests.conftest import plain_pdf

parser = ConnectWebhookParser()


def _completed_payload(content_pdf: bytes, summary_pdf: bytes) -> str:
    return json.dumps(
        {
            "event": "envelope-completed",
            "data": {
                "envelopeId": "abc-123",
                "envelopeSummary": {
                    "status": "completed",
                    "envelopeDocuments": [
                        {
                            "documentId": "1",
                            "name": "Consulting Services Agreement",
                            "type": "content",
                            "PDFBytes": base64.b64encode(content_pdf).decode(),
                        },
                        {
                            "documentId": "certificate",
                            "name": "Summary",
                            "type": "summary",
                            "PDFBytes": base64.b64encode(summary_pdf).decode(),
                        },
                    ],
                },
            },
        }
    )


def test_parses_completed_envelope_with_signed_form_values(filled_pdf: bytes) -> None:
    envelope = parser.parse(_completed_payload(filled_pdf, plain_pdf()))

    assert envelope.envelope_id == "abc-123"
    assert envelope.status == "completed"
    assert envelope.is_completed
    assert len(envelope.documents) == 2

    content = envelope.documents[0]
    assert content.document_id == "1"
    assert content.type == "content"
    assert content.pdf_bytes == filled_pdf
    assert content.fields["party.name"] == "Jane Doe"
    assert content.fields["sig.date"] == "2026-09-14"
    assert content.fields["agree.terms"] == "true"
    assert content.fields["party.email"] == "", "unfilled field reads as empty"

    summary = envelope.documents[1]
    assert summary.document_id == "certificate"
    assert not summary.fields, "summary document has no AcroForm"

    assert envelope.fields()["party.name"] == "Jane Doe"


def test_parses_regardless_of_status_when_no_documents() -> None:
    envelope = parser.parse(
        '{"event": "envelope-sent",'
        ' "data": {"envelopeId": "no-docs-1", "envelopeSummary": {"status": "sent"}}}'
    )
    assert envelope.envelope_id == "no-docs-1"
    assert envelope.status == "sent"
    assert not envelope.is_completed
    assert envelope.documents == ()
    assert envelope.fields() == {}


def test_parses_bytes_overload(filled_pdf: bytes) -> None:
    payload = _completed_payload(filled_pdf, plain_pdf()).encode()
    assert parser.parse(payload).envelope_id == "abc-123"


def test_malformed_json_throws() -> None:
    with pytest.raises(WebhookParseError):
        parser.parse("{not valid json")


def test_empty_or_none_payload_throws() -> None:
    with pytest.raises(WebhookParseError):
        parser.parse("  ")
    with pytest.raises(WebhookParseError):
        parser.parse(None)


def test_missing_data_object_throws() -> None:
    with pytest.raises(WebhookParseError):
        parser.parse('{"event":"x"}')


def test_invalid_base64_document_throws() -> None:
    payload = json.dumps(
        {
            "data": {
                "envelopeId": "bad-doc",
                "envelopeSummary": {
                    "status": "completed",
                    "envelopeDocuments": [
                        {
                            "documentId": "1",
                            "name": "x",
                            "type": "content",
                            "PDFBytes": "@@@notbase64@@@",
                        }
                    ],
                },
            }
        }
    )
    with pytest.raises(WebhookParseError, match="Document '1' has invalid base64 PDFBytes"):
        parser.parse(payload)
