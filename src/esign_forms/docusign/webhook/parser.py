from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from esign_forms.form.reader import FormReader


class WebhookParseError(ValueError):
    """Raised for a malformed Connect payload (invalid JSON, missing ``data``, bad base64)."""


@dataclass(frozen=True)
class SignedDocument:
    """One document from a Connect notification, with its AcroForm values read out."""

    document_id: str | None
    name: str | None
    type: str | None
    pdf_bytes: bytes = field(repr=False)
    fields: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "fields", MappingProxyType(dict(self.fields or {})))


@dataclass(frozen=True)
class SignedEnvelope:
    envelope_id: str | None
    status: str | None
    documents: Sequence[SignedDocument] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "documents", tuple(self.documents or ()))

    @property
    def is_completed(self) -> bool:
        return (self.status or "").lower() == "completed"

    def fields(self) -> dict[str, str]:
        """All documents' fields merged in document order (later documents win on clashes)."""
        merged: dict[str, str] = {}
        for document in self.documents:
            merged.update(document.fields)
        return merged


class ConnectWebhookParser:
    """Parses a DocuSign Connect **JSON** (eSignature) notification into a :class:`SignedEnvelope`.

    The base64 PDF lives at ``data.envelopeSummary.envelopeDocuments[].PDFBytes`` (note:
    ``PDFBytes``, not the SDK model's ``documentBase64``). Notifications without documents parse
    into an empty ``documents`` tuple regardless of status.
    """

    def __init__(self, form_reader: FormReader | None = None) -> None:
        self._form_reader = form_reader or FormReader()

    def parse(self, payload: bytes | str | None) -> SignedEnvelope:
        if payload is None:
            raise WebhookParseError("payload must not be null")
        text = payload.decode("utf-8") if isinstance(payload, bytes | bytearray) else payload
        if not text.strip():
            raise WebhookParseError("payload must not be empty")
        try:
            root = json.loads(text)
        except json.JSONDecodeError as e:
            raise WebhookParseError("Payload is not valid JSON") from e

        data = root.get("data") if isinstance(root, dict) else None
        if not isinstance(data, dict):
            raise WebhookParseError("Payload is missing the 'data' object")

        envelope_id = _text(data, "envelopeId")
        summary = data.get("envelopeSummary")
        status = _text(summary, "status") if isinstance(summary, dict) else None

        documents: list[SignedDocument] = []
        if isinstance(summary, dict):
            envelope_documents = summary.get("envelopeDocuments")
            if isinstance(envelope_documents, list):
                for node in envelope_documents:
                    document = self._to_signed_document(node) if isinstance(node, dict) else None
                    if document is not None:
                        documents.append(document)
        return SignedEnvelope(envelope_id, status, documents)

    def _to_signed_document(self, node: dict[str, Any]) -> SignedDocument | None:
        encoded = _text(node, "PDFBytes")
        if encoded is None or not encoded.strip():
            return None
        try:
            pdf_bytes = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as e:
            raise WebhookParseError(
                f"Document '{_text(node, 'documentId')}' has invalid base64 PDFBytes"
            ) from e
        return SignedDocument(
            document_id=_text(node, "documentId"),
            name=_text(node, "name"),
            type=_text(node, "type"),
            pdf_bytes=pdf_bytes,
            fields=self._form_reader.read(pdf_bytes),
        )


def _text(node: dict[str, Any], key: str) -> str | None:
    """Jackson ``asText()`` semantics: missing/null -> None, scalars -> their string form."""
    value = node.get(key)
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dict | list):
        return ""
    return str(value)
