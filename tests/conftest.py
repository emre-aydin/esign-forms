from __future__ import annotations

import io
import os
import sys
from pathlib import Path

# WeasyPrint locates Pango/GLib via ctypes.util.find_library, which honours
# DYLD_FALLBACK_LIBRARY_PATH at lookup time. macOS strips DYLD_* variables across `uv run`, so
# point it at Homebrew's lib dir here (before WeasyPrint is imported) when it isn't set.
if sys.platform == "darwin" and not os.environ.get("DYLD_FALLBACK_LIBRARY_PATH"):
    for _lib in ("/opt/homebrew/lib", "/usr/local/lib"):
        if Path(_lib, "libpango-1.0.dylib").exists():
            os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = _lib
            break

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, NameObject, TextStringObject

from contract_generator import ContractData, ContractGenerator
from contract_generator.form._acroform import acroform_of, on_states, walk_fields, widgets_of


def sample_data() -> ContractData:
    return (
        ContractData.builder()
        .put("title", "Consulting Services Agreement")
        .put("provider", "Acme Consulting LLC")
        .put("client", "Globex Corporation")
        .put("effectiveDate", "2026-09-13")
        .put("recital", "The Provider agrees to deliver consulting services to the Client.")
        .build()
    )


def fields_by_name(pdf: bytes | PdfWriter) -> dict[str, DictionaryObject]:
    doc = pdf if isinstance(pdf, PdfWriter) else PdfReader(io.BytesIO(pdf))
    form = acroform_of(doc)
    assert form is not None, "PDF should contain an AcroForm"
    return {node.name: node.field for node in walk_fields(form)}


def check_checkbox(field: DictionaryObject) -> None:
    """Checks a checkbox the way a viewer does: set ``/V`` and each widget's ``/AS``."""
    on = NameObject(on_states(field)[0])
    field[NameObject("/V")] = on
    for widget in widgets_of(field):
        widget[NameObject("/AS")] = on


def fill_sample_fields(pdf: bytes) -> bytes:
    """Simulates a user filling in the generated PDF. ``party.email`` is left unfilled."""
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(pdf)))
    fields = fields_by_name(writer)
    fields["party.name"][NameObject("/V")] = TextStringObject("Jane Doe")
    fields["sig.date"][NameObject("/V")] = TextStringObject("2026-09-14")
    check_checkbox(fields["agree.terms"])
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def plain_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(612, 792)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


@pytest.fixture(scope="session")
def generated_pdf() -> bytes:
    return ContractGenerator().generate("contract", sample_data())


@pytest.fixture(scope="session")
def filled_pdf(generated_pdf: bytes) -> bytes:
    return fill_sample_fields(generated_pdf)
