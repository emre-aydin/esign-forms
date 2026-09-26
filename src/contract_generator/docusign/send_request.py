from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from contract_generator.docusign._validation import require_text


@dataclass(frozen=True)
class Signer:
    """An envelope recipient who signs; ``routing_order`` starts at 1."""

    name: str
    email: str
    routing_order: int = 1

    def __post_init__(self) -> None:
        require_text(self.name, "name")
        require_text(self.email, "email")
        if self.routing_order < 1:
            raise ValueError("routing_order must be >= 1")


@dataclass(frozen=True)
class SendRequest:
    """Everything needed to send one PDF for signature."""

    document_name: str
    pdf_bytes: bytes = field(repr=False)
    email_subject: str
    signers: Sequence[Signer]

    def __post_init__(self) -> None:
        require_text(self.document_name, "document_name")
        if not self.pdf_bytes:
            raise ValueError("pdf_bytes must not be empty")
        require_text(self.email_subject, "email_subject")
        if not self.signers:
            raise ValueError("signers must not be empty")
        object.__setattr__(self, "signers", tuple(self.signers))
