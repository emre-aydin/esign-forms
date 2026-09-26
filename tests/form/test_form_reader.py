from __future__ import annotations

import io
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject

from esign_forms import FormGenerator
from esign_forms.form import AcroFormPostProcessor, FormReader, ReadError
from esign_forms.render import HtmlToPdfRenderer
from tests.conftest import fields_by_name, plain_pdf


def test_reads_filled_and_unfilled_field_values(filled_pdf: bytes) -> None:
    values = FormReader().read(filled_pdf)
    assert values["party.name"] == "Jane Doe"
    assert values["sig.date"] == "2026-09-14"
    assert values["agree.terms"] == "true"
    assert values["party.email"] == "", "unfilled text field should read as empty"
    # Only terminal fields are returned; dotted-name parents are excluded.
    assert not {"party", "sig", "agree"} & values.keys()


def test_unchecked_checkbox_reads_false(generated_pdf: bytes) -> None:
    assert FormReader().read(generated_pdf)["agree.terms"] == "false"


def test_reads_through_esign_forms_facade(filled_pdf: bytes) -> None:
    values = FormGenerator().read_values(filled_pdf)
    assert values["party.name"] == "Jane Doe"
    assert values["agree.terms"] == "true"


def test_reads_from_path_and_stream(filled_pdf: bytes, tmp_path: Path) -> None:
    pdf_path = tmp_path / "filled.pdf"
    pdf_path.write_bytes(filled_pdf)
    assert FormReader().read(pdf_path)["party.name"] == "Jane Doe"
    assert FormReader().read(str(pdf_path))["party.name"] == "Jane Doe"
    stream = io.BytesIO(filled_pdf)
    assert FormGenerator().read_values(stream)["party.name"] == "Jane Doe"
    assert not stream.closed, "caller owns the stream"


def test_selected_radio_reads_export_value() -> None:
    pdf = AcroFormPostProcessor().process(
        HtmlToPdfRenderer().render(
            '<html><body style="font-family: EsignFormsFont"><form>'
            '<input type="radio" name="tier" value="basic" />'
            '<input type="radio" name="tier" value="pro" />'
            "</form></body></html>"
        )
    )
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(pdf)))
    group = fields_by_name(writer)["tier"]
    group[NameObject("/V")] = NameObject("/1")
    out = io.BytesIO()
    writer.write(out)
    assert FormReader().read(out.getvalue()) == {"tier": "pro"}


def test_pdf_without_acroform_yields_empty_map() -> None:
    assert FormReader().read(plain_pdf()) == {}


def test_unreadable_input_raises_read_error(tmp_path: Path) -> None:
    with pytest.raises(ReadError):
        FormReader().read(b"definitely not a pdf")
    with pytest.raises(ReadError):
        FormReader().read(tmp_path / "missing.pdf")
