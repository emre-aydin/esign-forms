from __future__ import annotations

from typing import Protocol

from docusign_esign import EnvelopeDefinition


class DocuSignClient(Protocol):
    """Creates an envelope and returns its id. Abstracted so the sender can be unit-tested."""

    def create_envelope(self, envelope: EnvelopeDefinition) -> str: ...
