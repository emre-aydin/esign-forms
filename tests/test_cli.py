from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
from pathlib import Path
from typing import Any

import pytest

from esign_forms import cli
from esign_forms.docusign import DocuSignConfig, DocuSignError, DocuSignSender, EnvelopeFactory
from tests.conftest import EXAMPLE_TEMPLATE, fields_by_name, plain_pdf
from tests.docusign.test_sender import FakeClient

DOCUSIGN_ENV = {
    "DOCUSIGN_ACCOUNT_ID": "acct",
    "DOCUSIGN_OAUTH_BASE_PATH": "account-d.docusign.com",
    "DOCUSIGN_INTEGRATION_KEY": "ik",
    "DOCUSIGN_USER_ID": "user",
    "DOCUSIGN_PRIVATE_KEY": "PEM",
}
GENERATE_INPUT = {
    "data": {"client": "Globex Corporation"},
    "expectedFields": ["party.name"],
    "requiredFields": ["party.name"],
}
ENVELOPE_INPUT = {
    "documentName": "Agreement",
    "emailSubject": "Please sign",
    "signers": [{"name": "Jane Doe", "email": "jane@example.com", "routingOrder": 2}],
}


class Result:
    def __init__(self, code: int, stdout: bytes, stderr: bytes) -> None:
        self.code = code
        self.stdout = stdout
        self.stderr = stderr

    def json(self) -> Any:
        return json.loads(self.stdout)

    def error(self) -> dict[str, str]:
        return json.loads(self.stderr)["error"]  # type: ignore[no-any-return]


def run(*argv: str, stdin: bytes = b"", env: dict[str, str] | None = None) -> Result:
    out, err = io.BytesIO(), io.BytesIO()
    code = cli.main(list(argv), stdin=io.BytesIO(stdin), stdout=out, stderr=err, env=env or {})
    return Result(code, out.getvalue(), err.getvalue())


def write_json(path: Path, value: object) -> str:
    path.write_text(json.dumps(value))
    return str(path)


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch) -> FakeClient:
    client = FakeClient("env-42")

    def factory(config: DocuSignConfig) -> DocuSignSender:
        assert config.private_key == b"PEM"
        return DocuSignSender(EnvelopeFactory(), client)

    monkeypatch.setattr(cli, "sender_factory", factory)
    return client


def test_generate_writes_pdf_to_stdout_with_json_from_stdin() -> None:
    result = run(
        "generate",
        "--template",
        str(EXAMPLE_TEMPLATE),
        "--input",
        "-",
        stdin=json.dumps(GENERATE_INPUT).encode(),
    )
    assert result.code == 0, result.stderr
    assert result.stdout.startswith(b"%PDF")
    assert "party.name" in fields_by_name(result.stdout)


def test_generate_reads_template_from_stdin_and_writes_output_file(tmp_path: Path) -> None:
    output = tmp_path / "out.pdf"
    template = (
        '<html><body><form><input name="a.b" style="min-width:1em"/>{{ x }}</form></body></html>'
    )
    result = run(
        "generate",
        "--template",
        "-",
        "--input",
        write_json(tmp_path / "in.json", {"data": {"x": 1}}),
        "--output",
        str(output),
        stdin=template.encode(),
    )
    assert result.code == 0, result.stderr
    assert result.stdout == b""
    assert "a.b" in fields_by_name(output.read_bytes())


def test_rejects_more_than_one_stdin_input() -> None:
    result = run("generate", "--template", "-", "--input", "-")
    assert result.code == cli.EXIT_INVALID_INPUT
    assert result.error()["type"] == "invalid_input"
    assert "only one input" in result.error()["message"]


def test_usage_errors_are_reported_as_json() -> None:
    result = run("generate", "--template", "x.html")
    assert result.code == cli.EXIT_INVALID_INPUT
    assert "--input" in result.error()["message"]


def test_generate_reports_missing_expected_fields(tmp_path: Path) -> None:
    result = run(
        "generate",
        "--template",
        str(EXAMPLE_TEMPLATE),
        "--input",
        write_json(tmp_path / "in.json", {"expectedFields": ["nope"]}),
    )
    assert result.code == cli.EXIT_INVALID_INPUT
    assert result.error()["message"] == "Expected form fields are missing: [nope]"


@pytest.mark.parametrize(
    ("spec", "message"),
    [
        ({"data": []}, "'data' must be an object"),
        ({"expectedFields": "x"}, "'expectedFields' must be an array of strings"),
        ({"bogus": 1}, "unknown input key(s): bogus"),
    ],
)
def test_generate_validates_input_json(tmp_path: Path, spec: object, message: str) -> None:
    result = run(
        "generate",
        "--template",
        str(EXAMPLE_TEMPLATE),
        "--input",
        write_json(tmp_path / "i.json", spec),
    )
    assert result.code == cli.EXIT_INVALID_INPUT
    assert result.error()["message"] == message


def test_invalid_json_and_missing_template(tmp_path: Path) -> None:
    bad = run("generate", "--template", str(EXAMPLE_TEMPLATE), "--input", "-", stdin=b"{nope")
    assert bad.code == cli.EXIT_INVALID_INPUT
    assert "not valid JSON" in bad.error()["message"]

    missing = run("generate", "--template", str(tmp_path / "x.html"), "--input", "-", stdin=b"{}")
    assert missing.code == cli.EXIT_INVALID_INPUT
    assert "template not found" in missing.error()["message"]


def test_send_renders_and_sends(tmp_path: Path, fake_client: FakeClient) -> None:
    spec = {**GENERATE_INPUT, **ENVELOPE_INPUT}
    result = run(
        "send",
        "--template",
        str(EXAMPLE_TEMPLATE),
        "--input",
        write_json(tmp_path / "i.json", spec),
        env=DOCUSIGN_ENV,
    )
    assert result.code == 0, result.stderr
    assert result.json() == {"envelopeId": "env-42"}
    assert fake_client.captured is not None
    signer = fake_client.captured.recipients.signers[0]
    assert (signer.email, signer.routing_order) == ("jane@example.com", "2")


def test_send_validates_envelope_fields_and_credentials(
    tmp_path: Path, fake_client: FakeClient
) -> None:
    no_signers = run(
        "send",
        "--template",
        str(EXAMPLE_TEMPLATE),
        "--input",
        write_json(tmp_path / "a.json", {**ENVELOPE_INPUT, "signers": []}),
        env=DOCUSIGN_ENV,
    )
    assert no_signers.code == cli.EXIT_INVALID_INPUT
    assert no_signers.error()["message"] == "'signers' must be a non-empty array"

    no_env = run(
        "send",
        "--template",
        str(EXAMPLE_TEMPLATE),
        "--input",
        write_json(tmp_path / "b.json", ENVELOPE_INPUT),
    )
    assert no_env.code == cli.EXIT_INVALID_INPUT
    assert fake_client.captured is None


def test_send_pdf_reads_pdf_from_stdin(tmp_path: Path, fake_client: FakeClient) -> None:
    result = run(
        "send-pdf",
        "--pdf",
        "-",
        "--input",
        write_json(tmp_path / "i.json", ENVELOPE_INPUT),
        stdin=b"%PDF-1.4 fake",
        env=DOCUSIGN_ENV,
    )
    assert result.code == 0, result.stderr
    assert result.json() == {"envelopeId": "env-42"}
    assert fake_client.captured is not None
    assert base64.b64decode(fake_client.captured.documents[0].document_base64) == b"%PDF-1.4 fake"


def test_docusign_errors_exit_3(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingClient:
        def create_envelope(self, envelope: object) -> str:
            raise DocuSignError("boom")

    monkeypatch.setattr(
        cli, "sender_factory", lambda config: DocuSignSender(EnvelopeFactory(), FailingClient())
    )
    result = run(
        "send-pdf",
        "--pdf",
        "-",
        "--input",
        write_json(tmp_path / "i.json", ENVELOPE_INPUT),
        stdin=b"%PDF",
        env=DOCUSIGN_ENV,
    )
    assert result.code == cli.EXIT_DOCUSIGN
    assert result.error() == {"type": "docusign", "message": "boom"}


def test_read_prints_field_values(filled_pdf: bytes) -> None:
    result = run("read", "--pdf", "-", stdin=filled_pdf)
    assert result.code == 0, result.stderr
    fields = result.json()["fields"]
    assert fields["party.name"] == "Jane Doe"
    assert fields["agree.terms"] == "true"


def test_read_rejects_non_pdf() -> None:
    result = run("read", "--pdf", "-", stdin=b"not a pdf")
    assert result.code == cli.EXIT_INVALID_INPUT


def _webhook_body(pdf: bytes) -> bytes:
    return json.dumps(
        {
            "data": {
                "envelopeId": "abc-123",
                "envelopeSummary": {
                    "status": "completed",
                    "envelopeDocuments": [
                        {
                            "documentId": "1",
                            "name": "Agreement",
                            "type": "content",
                            "PDFBytes": base64.b64encode(pdf).decode(),
                        },
                        {
                            "documentId": "certificate",
                            "name": "Summary",
                            "type": "summary",
                            "PDFBytes": base64.b64encode(plain_pdf()).decode(),
                        },
                    ],
                },
            }
        }
    ).encode()


def _sign(body: bytes, secret: str) -> str:
    return base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()


def test_parse_webhook_verifies_hmac_and_writes_pdfs(filled_pdf: bytes, tmp_path: Path) -> None:
    body = _webhook_body(filled_pdf)
    result = run(
        "parse-webhook",
        "--input",
        "-",
        "--signature",
        "bm9wZQ==",
        "--signature",
        _sign(body, "new"),
        "--pdf-dir",
        str(tmp_path / "pdfs"),
        stdin=body,
        env={cli.HMAC_SECRET_ENV: "old, new"},
    )
    assert result.code == 0, result.stderr
    out = result.json()
    assert (out["envelopeId"], out["status"], out["completed"]) == ("abc-123", "completed", True)
    content, summary = out["documents"]
    assert content["fields"]["party.name"] == "Jane Doe"
    assert Path(content["pdfPath"]).read_bytes() == filled_pdf
    assert Path(summary["pdfPath"]).name == "certificate.pdf"
    assert summary["fields"] == {}


def test_parse_webhook_rejects_bad_signature(filled_pdf: bytes) -> None:
    body = _webhook_body(filled_pdf)
    result = run(
        "parse-webhook",
        "--input",
        "-",
        "--signature",
        _sign(body, "wrong"),
        stdin=body,
        env={cli.HMAC_SECRET_ENV: "secret"},
    )
    assert result.code == cli.EXIT_HMAC
    assert result.error()["type"] == "hmac"
    assert result.stdout == b""


def test_parse_webhook_requires_secret_or_no_verify(filled_pdf: bytes) -> None:
    body = _webhook_body(filled_pdf)
    assert run("parse-webhook", "--input", "-", stdin=body).code == cli.EXIT_INVALID_INPUT

    result = run("parse-webhook", "--input", "-", "--no-verify", stdin=body)
    assert result.code == 0, result.stderr
    assert "pdfPath" not in result.json()["documents"][0]


def test_parse_webhook_rejects_malformed_payload() -> None:
    result = run("parse-webhook", "--input", "-", "--no-verify", stdin=b"{}")
    assert result.code == cli.EXIT_INVALID_INPUT
    assert "data" in result.error()["message"]


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    assert run("--version").code == 0
    assert capsys.readouterr().out.strip()
