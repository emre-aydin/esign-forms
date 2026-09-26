from __future__ import annotations

from pathlib import Path

import pytest

from contract_generator.docusign import DocuSignConfig, DocuSignSender, EnvelopeFactory
from contract_generator.temporal import ContractActivities, ContractSigningRequest, SignerInfo
from tests.conftest import fields_by_name
from tests.docusign.test_sender import FakeClient


def _request() -> ContractSigningRequest:
    return ContractSigningRequest(
        template_name="contract",
        parameters={
            "title": "Consulting Services Agreement",
            "provider": "Acme Consulting LLC",
            "client": "Globex Corporation",
            "effectiveDate": "2026-09-13",
            "recital": "The Provider agrees to deliver consulting services.",
        },
        expected_field_names=frozenset({"party.name", "party.email", "sig.name"}),
        required_field_names=frozenset({"party.name"}),
        document_name="Consulting Agreement",
        email_subject="Please sign",
        signers=(SignerInfo("Jane Doe", "jane@example.com"),),
    )


def test_generate_pdf_renders_bundled_template_into_acroform() -> None:
    pdf = ContractActivities(env={}).generate_pdf(_request())
    assert pdf
    assert "party.name" in fields_by_name(pdf)


def test_send_to_docusign_builds_config_from_env(tmp_path: Path) -> None:
    key = tmp_path / "key.pem"
    key.write_bytes(b"PEM")
    env = {
        "DOCUSIGN_ACCOUNT_ID": "acct",
        "DOCUSIGN_OAUTH_BASE_PATH": "account-d.docusign.com",
        "DOCUSIGN_INTEGRATION_KEY": "ik",
        "DOCUSIGN_USER_ID": "user",
        "DOCUSIGN_PRIVATE_KEY_PATH": str(key),
    }
    seen: list[DocuSignConfig] = []
    client = FakeClient("env-1")

    def factory(config: DocuSignConfig) -> DocuSignSender:
        seen.append(config)
        return DocuSignSender(EnvelopeFactory(), client)

    activities = ContractActivities(env=env, sender_factory=factory)
    assert activities.send_to_docusign(b"%PDF-1.4", _request()) == "env-1"
    assert seen[0].private_key == b"PEM"
    assert seen[0].account_id == "acct"
    assert client.captured is not None
    assert client.captured.recipients.signers[0].email == "jane@example.com"

    inline = ContractActivities(
        env={**env, "DOCUSIGN_PRIVATE_KEY": "INLINE"}, sender_factory=factory
    )
    inline.send_to_docusign(b"%PDF-1.4", _request())
    assert seen[1].private_key == b"INLINE"


def test_send_to_docusign_requires_private_key() -> None:
    with pytest.raises(RuntimeError, match="DOCUSIGN_PRIVATE_KEY or DOCUSIGN_PRIVATE_KEY_PATH"):
        ContractActivities(env={}).send_to_docusign(b"%PDF", _request())


def test_request_normalizes_none_collections() -> None:
    request = ContractSigningRequest("contract", None, None, None, "d", "s", None)  # type: ignore[arg-type]
    assert request.parameters == {}
    assert request.expected_field_names == frozenset()
    assert request.signers == ()
