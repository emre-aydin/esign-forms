from __future__ import annotations

import io
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject

from contract_generator import ContractGenerator
from contract_generator.form import AcroFormPostProcessor, ContractFormReader, ReadError
from contract_generator.render import HtmlToPdfRenderer
from tests.conftest import fields_by_name, plain_pdf


def test_reads_filled_and_unfilled_field_values(filled_pdf: bytes) -> None:
    values = ContractFormReader().read(filled_pdf)
    assert values["party.name"] == "Jane Doe"
    assert values["sig.date"] == "2026-09-14"
    assert values["agree.terms"] == "true"
    assert values["party.email"] == "", "unfilled text field should read as empty"
    # Only terminal fields are returned; dotted-name parents are excluded.
    assert not {"party", "sig", "agree"} & values.keys()


def test_unchecked_checkbox_reads_false(generated_pdf: bytes) -> None:
    assert ContractFormReader().read(generated_pdf)["agree.terms"] == "false"


def test_reads_through_contract_generator_facade(filled_pdf: bytes) -> None:
    values = ContractGenerator().read_values(filled_pdf)
    assert values["party.name"] == "Jane Doe"
    assert values["agree.terms"] == "true"


def test_reads_from_path_and_stream(filled_pdf: bytes, tmp_path: Path) -> None:
    pdf_path = tmp_path / "filled.pdf"
    pdf_path.write_bytes(filled_pdf)
    assert ContractFormReader().read(pdf_path)["party.name"] == "Jane Doe"
    assert ContractFormReader().read(str(pdf_path))["party.name"] == "Jane Doe"
    stream = io.BytesIO(filled_pdf)
    assert ContractGenerator().read_values(stream)["party.name"] == "Jane Doe"
    assert not stream.closed, "caller owns the stream"


def test_selected_radio_reads_export_value() -> None:
    pdf = AcroFormPostProcessor().process(
        HtmlToPdfRenderer().render(
            '<html><body style="font-family: ContractFont"><form>'
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
    assert ContractFormReader().read(out.getvalue()) == {"tier": "pro"}


def test_pdf_without_acroform_yields_empty_map() -> None:
    assert ContractFormReader().read(plain_pdf()) == {}


def test_unreadable_input_raises_read_error(tmp_path: Path) -> None:
    with pytest.raises(ReadError):
        ContractFormReader().read(b"definitely not a pdf")
    with pytest.raises(ReadError):
        ContractFormReader().read(tmp_path / "missing.pdf")
