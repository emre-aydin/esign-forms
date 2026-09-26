"""``esign-forms`` command-line interface: a JSON-in/JSON-out wrapper meant for subprocess use.

Every file argument accepts ``-`` for stdin (inputs) or stdout (outputs); at most one input per
invocation may be ``-``. Results are written to stdout as JSON (or PDF bytes for ``generate``).
Failures write ``{"error": {"type": ..., "message": ...}}`` to stderr and exit non-zero:

====  ==================  ==============================================================
code  ``type``            meaning
====  ==================  ==============================================================
0                         success
1     ``internal``        unexpected error
2     ``invalid_input``   bad arguments, unreadable files, invalid JSON/template/PDF, or
                          missing expected/required form fields
3     ``docusign``        authenticating with or calling DocuSign failed
4     ``hmac``            Connect webhook HMAC verification failed
5     ``render``          HTML-to-PDF rendering failed (e.g. Pango missing)
====  ==================  ==============================================================
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import IO, Any, NoReturn

from jinja2 import TemplateError

from esign_forms.docusign.config import DocuSignConfig
from esign_forms.docusign.errors import DocuSignError
from esign_forms.docusign.send_request import SendRequest, Signer
from esign_forms.docusign.sender import DocuSignSender
from esign_forms.docusign.webhook.hmac_verifier import ConnectHmacVerifier
from esign_forms.docusign.webhook.parser import ConnectWebhookParser
from esign_forms.form.post_processor import PostProcessError
from esign_forms.form.reader import ReadError
from esign_forms.generator import FormGenerator
from esign_forms.render import RenderError

EXIT_OK = 0
EXIT_INTERNAL = 1
EXIT_INVALID_INPUT = 2
EXIT_DOCUSIGN = 3
EXIT_HMAC = 4
EXIT_RENDER = 5

STDIO = "-"
HMAC_SECRET_ENV = "DOCUSIGN_CONNECT_HMAC_SECRET"

sender_factory: Callable[[DocuSignConfig], DocuSignSender] = DocuSignSender.for_live_docusign
"""Builds the sender for ``send``/``send-pdf``; replaceable in tests."""


class CliError(Exception):
    def __init__(self, error_type: str, message: str, exit_code: int) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.exit_code = exit_code


def _invalid(message: str) -> CliError:
    return CliError("invalid_input", message, EXIT_INVALID_INPUT)


@dataclass
class _Io:
    stdin: IO[bytes]
    stdout: IO[bytes]
    stderr: IO[bytes]
    env: Mapping[str, str]


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise _invalid(f"{self.prog}: {message}")


def _package_version() -> str:
    try:
        return version("esign-forms")
    except PackageNotFoundError:
        return "unknown"


def _build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="esign-forms",
        description="Render fillable PDFs from HTML templates, send them to DocuSign, "
        "and read filled values back. Use '-' for stdin/stdout.",
    )
    parser.add_argument("--version", action="version", version=_package_version())
    sub = parser.add_subparsers(dest="command", required=True, parser_class=_Parser)

    generate = sub.add_parser("generate", help="render a template into a fillable PDF")
    generate.add_argument("--template", required=True, help="Jinja2 HTML template file, or -")
    generate.add_argument(
        "--input", required=True, help="JSON {data, expectedFields?, requiredFields?}, or -"
    )
    generate.add_argument("--output", default=STDIO, help="PDF output file (default: stdout)")

    send = sub.add_parser("send", help="render a template and send it to DocuSign")
    send.add_argument("--template", required=True, help="Jinja2 HTML template file, or -")
    send.add_argument(
        "--input",
        required=True,
        help="JSON {data, expectedFields?, requiredFields?, documentName, emailSubject, "
        "signers}, or -",
    )

    send_pdf = sub.add_parser("send-pdf", help="send an existing PDF to DocuSign")
    send_pdf.add_argument("--pdf", required=True, help="PDF file, or -")
    send_pdf.add_argument(
        "--input", required=True, help="JSON {documentName, emailSubject, signers}, or -"
    )

    read = sub.add_parser("read", help="print the AcroForm field values of a PDF")
    read.add_argument("--pdf", required=True, help="PDF file, or -")

    webhook = sub.add_parser(
        "parse-webhook", help="verify and parse a DocuSign Connect JSON notification"
    )
    webhook.add_argument("--input", required=True, help="raw Connect request body, or -")
    webhook.add_argument(
        "--signature",
        action="append",
        default=[],
        help="an X-DocuSign-Signature-N header value (repeatable)",
    )
    webhook.add_argument(
        "--no-verify",
        action="store_true",
        help=f"skip HMAC verification (otherwise the secret comes from ${HMAC_SECRET_ENV})",
    )
    webhook.add_argument("--pdf-dir", help="write the signed PDFs into this directory")
    return parser


_STDIN_ARGS = ("template", "input", "pdf")


def main(
    argv: Sequence[str] | None = None,
    *,
    stdin: IO[bytes] | None = None,
    stdout: IO[bytes] | None = None,
    stderr: IO[bytes] | None = None,
    env: Mapping[str, str] | None = None,
) -> int:
    io = _Io(
        stdin=stdin if stdin is not None else sys.stdin.buffer,
        stdout=stdout if stdout is not None else sys.stdout.buffer,
        stderr=stderr if stderr is not None else sys.stderr.buffer,
        env=os.environ if env is None else env,
    )
    try:
        try:
            args = _build_parser().parse_args(argv)
        except SystemExit as e:  # --help / --version
            return e.code if isinstance(e.code, int) else EXIT_OK
        stdin_args = [a for a in _STDIN_ARGS if getattr(args, a, None) == STDIO]
        if len(stdin_args) > 1:
            raise _invalid(f"only one input may be read from stdin, got: {', '.join(stdin_args)}")
        _COMMANDS[args.command](args, io)
        return EXIT_OK
    except CliError as e:
        return _fail(io, e.error_type, str(e), e.exit_code)
    except DocuSignError as e:
        return _fail(io, "docusign", str(e), EXIT_DOCUSIGN)
    except RenderError as e:
        message = f"{e}: {e.__cause__}" if e.__cause__ else str(e)
        return _fail(io, "render", message, EXIT_RENDER)
    except (ValueError, PostProcessError, ReadError, TemplateError, OSError) as e:
        return _fail(io, "invalid_input", str(e) or type(e).__name__, EXIT_INVALID_INPUT)
    except Exception as e:
        return _fail(io, "internal", f"{type(e).__name__}: {e}", EXIT_INTERNAL)


def _fail(io: _Io, error_type: str, message: str, code: int) -> int:
    _write_json(io.stderr, {"error": {"type": error_type, "message": message}})
    return code


def _write_json(stream: IO[bytes], value: object) -> None:
    stream.write(json.dumps(value, ensure_ascii=False).encode("utf-8") + b"\n")
    stream.flush()


def _read_bytes(path: str, io: _Io) -> bytes:
    if path == STDIO:
        return io.stdin.read()
    try:
        return Path(path).read_bytes()
    except OSError as e:
        raise _invalid(f"cannot read {path}: {e.strerror or e}") from e


def _read_json_object(path: str, io: _Io) -> dict[str, Any]:
    raw = _read_bytes(path, io)
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise _invalid(f"input is not valid JSON: {e}") from e
    if not isinstance(value, dict):
        raise _invalid("input JSON must be an object")
    return value


def _template_source(path: str, io: _Io) -> str | Path:
    if path == STDIO:
        try:
            return io.stdin.read().decode("utf-8")
        except UnicodeDecodeError as e:
            raise _invalid("template on stdin is not valid UTF-8") from e
    template = Path(path)
    if not template.is_file():
        raise _invalid(f"template not found: {path}")
    return template


# --- JSON input validation -------------------------------------------------------------------


def _check_keys(obj: Mapping[str, Any], allowed: set[str], where: str) -> None:
    unknown = sorted(set(obj) - allowed)
    if unknown:
        raise _invalid(f"unknown {where} key(s): {', '.join(unknown)}")


def _string(obj: Mapping[str, Any], key: str) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        raise _invalid(f"'{key}' must be a non-empty string")
    return value


def _string_set(obj: Mapping[str, Any], key: str) -> frozenset[str]:
    value = obj.get(key, [])
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise _invalid(f"'{key}' must be an array of strings")
    return frozenset(value)


def _data(obj: Mapping[str, Any]) -> dict[str, Any]:
    value = obj.get("data", {})
    if not isinstance(value, dict):
        raise _invalid("'data' must be an object")
    return value


def _signers(obj: Mapping[str, Any]) -> list[Signer]:
    value = obj.get("signers")
    if not isinstance(value, list) or not value:
        raise _invalid("'signers' must be a non-empty array")
    signers = []
    for i, item in enumerate(value):
        if not isinstance(item, dict):
            raise _invalid(f"signers[{i}] must be an object")
        _check_keys(item, {"name", "email", "routingOrder"}, f"signers[{i}]")
        routing_order = item.get("routingOrder", 1)
        if not isinstance(routing_order, int) or isinstance(routing_order, bool):
            raise _invalid(f"signers[{i}].routingOrder must be an integer")
        signers.append(Signer(_string(item, "name"), _string(item, "email"), routing_order))
    return signers


_GENERATE_KEYS = {"data", "expectedFields", "requiredFields"}
_ENVELOPE_KEYS = {"documentName", "emailSubject", "signers"}


def _generate_pdf(args: argparse.Namespace, spec: Mapping[str, Any], io: _Io) -> bytes:
    return FormGenerator().generate(
        _template_source(args.template, io),
        _data(spec),
        _string_set(spec, "expectedFields"),
        _string_set(spec, "requiredFields"),
    )


def _send(pdf: bytes, spec: Mapping[str, Any], io: _Io) -> None:
    request = SendRequest(
        _string(spec, "documentName"), pdf, _string(spec, "emailSubject"), _signers(spec)
    )
    envelope_id = sender_factory(DocuSignConfig.from_env(io.env)).send_for_signature(request)
    _write_json(io.stdout, {"envelopeId": envelope_id})


# --- commands --------------------------------------------------------------------------------


def _cmd_generate(args: argparse.Namespace, io: _Io) -> None:
    spec = _read_json_object(args.input, io)
    _check_keys(spec, _GENERATE_KEYS, "input")
    pdf = _generate_pdf(args, spec, io)
    if args.output == STDIO:
        io.stdout.write(pdf)
        io.stdout.flush()
    else:
        Path(args.output).write_bytes(pdf)


def _cmd_send(args: argparse.Namespace, io: _Io) -> None:
    spec = _read_json_object(args.input, io)
    _check_keys(spec, _GENERATE_KEYS | _ENVELOPE_KEYS, "input")
    # Validate the envelope fields before spending time on rendering.
    _string(spec, "documentName")
    _string(spec, "emailSubject")
    _signers(spec)
    _send(_generate_pdf(args, spec, io), spec, io)


def _cmd_send_pdf(args: argparse.Namespace, io: _Io) -> None:
    pdf = _read_bytes(args.pdf, io)
    spec = _read_json_object(args.input, io)
    _check_keys(spec, _ENVELOPE_KEYS, "input")
    _send(pdf, spec, io)


def _cmd_read(args: argparse.Namespace, io: _Io) -> None:
    fields = FormGenerator().read_values(_read_bytes(args.pdf, io))
    _write_json(io.stdout, {"fields": fields})


def _cmd_parse_webhook(args: argparse.Namespace, io: _Io) -> None:
    body = _read_bytes(args.input, io)
    if not args.no_verify:
        secrets = [s.strip() for s in io.env.get(HMAC_SECRET_ENV, "").split(",") if s.strip()]
        if not secrets:
            raise _invalid(f"set {HMAC_SECRET_ENV} or pass --no-verify")
        verifier = ConnectHmacVerifier()
        if not any(verifier.verify_any(body, args.signature, secret) for secret in secrets):
            raise CliError("hmac", "HMAC signature verification failed", EXIT_HMAC)

    envelope = ConnectWebhookParser().parse(body)
    pdf_dir = Path(args.pdf_dir) if args.pdf_dir else None
    if pdf_dir is not None:
        pdf_dir.mkdir(parents=True, exist_ok=True)

    documents = []
    for index, document in enumerate(envelope.documents, start=1):
        entry: dict[str, Any] = {
            "documentId": document.document_id,
            "name": document.name,
            "type": document.type,
            "fields": dict(document.fields),
        }
        if pdf_dir is not None:
            stem = re.sub(r"[^A-Za-z0-9._-]", "_", document.document_id or str(index))
            pdf_path = (pdf_dir / f"{stem}.pdf").resolve()
            pdf_path.write_bytes(document.pdf_bytes)
            entry["pdfPath"] = str(pdf_path)
        documents.append(entry)

    _write_json(
        io.stdout,
        {
            "envelopeId": envelope.envelope_id,
            "status": envelope.status,
            "completed": envelope.is_completed,
            "documents": documents,
        },
    )


_COMMANDS: dict[str, Callable[[argparse.Namespace, _Io], None]] = {
    "generate": _cmd_generate,
    "send": _cmd_send,
    "send-pdf": _cmd_send_pdf,
    "read": _cmd_read,
    "parse-webhook": _cmd_parse_webhook,
}


if __name__ == "__main__":
    sys.exit(main())
