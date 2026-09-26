import pytest

from contract_generator.docusign import DocuSignConfig, SendRequest, Signer


def test_signer_validation() -> None:
    assert Signer("A", "a@example.com").routing_order == 1
    with pytest.raises(ValueError, match="name must not be blank"):
        Signer(" ", "a@example.com")
    with pytest.raises(ValueError, match="email must not be blank"):
        Signer("A", "")
    with pytest.raises(ValueError, match="routing_order must be >= 1"):
        Signer("A", "a@example.com", 0)


def test_send_request_validation_and_copy() -> None:
    signers = [Signer("A", "a@example.com")]
    request = SendRequest("Doc", b"%PDF", "Subject", signers)
    signers.clear()
    assert len(request.signers) == 1
    with pytest.raises(ValueError, match="document_name"):
        SendRequest("", b"%PDF", "Subject", [Signer("A", "a@example.com")])
    with pytest.raises(ValueError, match="pdf_bytes"):
        SendRequest("Doc", b"", "Subject", [Signer("A", "a@example.com")])
    with pytest.raises(ValueError, match="email_subject"):
        SendRequest("Doc", b"%PDF", " ", [Signer("A", "a@example.com")])
    with pytest.raises(ValueError, match="signers"):
        SendRequest("Doc", b"%PDF", "Subject", [])


def test_config_validation_and_key_not_in_repr() -> None:
    config = DocuSignConfig("acct", "account-d.docusign.com", "ik", "user", b"secret-key")
    assert "secret-key" not in repr(config)
    with pytest.raises(ValueError, match="account_id"):
        DocuSignConfig("", "host", "ik", "user", b"k")
    with pytest.raises(ValueError, match="private_key"):
        DocuSignConfig("acct", "host", "ik", "user", b"")
