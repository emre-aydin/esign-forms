"""Workflow/activity payloads: plain dataclasses that Temporal's default JSON converter handles."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SignerInfo:
    name: str
    email: str
    routing_order: int = 1


@dataclass(frozen=True)
class FormSigningRequest:
    """Input of :class:`~esign_forms.temporal.workflow.FormSigningWorkflow`.

    ``None`` collections are normalized to empty ones; all collections are copied.
    """

    template_path: str
    """Path of the Jinja2 template file on the worker's filesystem."""

    parameters: dict[str, str] = field(default_factory=dict)
    expected_field_names: frozenset[str] = frozenset()
    required_field_names: frozenset[str] = frozenset()
    document_name: str = ""
    email_subject: str = ""
    signers: tuple[SignerInfo, ...] = ()

    def __post_init__(self) -> None:
        params: Mapping[str, str] | None = self.parameters
        expected: Iterable[str] | None = self.expected_field_names
        required: Iterable[str] | None = self.required_field_names
        signers: Iterable[SignerInfo] | None = self.signers
        object.__setattr__(self, "parameters", dict(params or {}))
        object.__setattr__(self, "expected_field_names", frozenset(expected or ()))
        object.__setattr__(self, "required_field_names", frozenset(required or ()))
        object.__setattr__(self, "signers", tuple(signers or ()))
