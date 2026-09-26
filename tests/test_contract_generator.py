from __future__ import annotations

import io

import pytest
from pypdf import PdfReader

from contract_generator import ContractGenerator
from contract_generator.form import PostProcessError
from contract_generator.form._acroform import FF_REQUIRED, acroform_of
from tests.conftest import fields_by_name, sample_data

SIGNATURE_FIELD = "DocusignSignHere1"
EXPECTED_FIELDS = frozenset(
    {
        "party.name",
        "party.email",
        "party.notes",
        "agree.terms",
        "sig.name",
        "sig.title",
        "sig.date",
        SIGNATURE_FIELD,
    }
)


def test_generates_pdf_with_expected_fillable_fields() -> None:
    pdf = ContractGenerator().generate("contract", sample_data(), EXPECTED_FIELDS)
    assert pdf

    form = acroform_of(PdfReader(io.BytesIO(pdf)))
    assert form is not None
    assert form["/NeedAppearances"] == True, "NeedAppearances should be set"  # noqa: E712

    by_name = fields_by_name(pdf)
    assert by_name.keys() >= EXPECTED_FIELDS, f"All expected fields present; got {by_name.keys()}"

    name = by_name["party.name"]
    assert name["/FT"] == "/Tx"
    assert not int(name.get("/Ff", 0)) & 1, "text field should be fillable (not read-only)"
    assert by_name["agree.terms"]["/FT"] == "/Btn"
    assert by_name[SIGNATURE_FIELD]["/FT"] == "/Tx", "DocuSign SignHere field should be present"
    assert int(by_name["party.notes"].get("/Ff", 0)) & (1 << 12), "textarea is multiline"


def test_dotted_names_form_a_field_hierarchy() -> None:
    by_name = fields_by_name(ContractGenerator().generate("contract", sample_data()))
    for parent in ("party", "agree", "sig"):
        assert parent in by_name
        assert "/FT" not in by_name[parent], f"{parent} should be a non-terminal field"
    assert by_name["party.name"]["/T"] == "name"


def test_renders_dynamic_template_content() -> None:
    pdf = ContractGenerator().generate("contract", sample_data())
    text = "".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)
    assert "Consulting Services Agreement" in text, "title rendered"
    assert "Globex Corporation" in text, "client rendered"


def test_accepts_plain_mapping_as_data() -> None:
    pdf = ContractGenerator().generate("contract", {"client": "Initech"})
    text = "".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)
    assert "Initech" in text


def test_missing_expected_field_fails() -> None:
    with pytest.raises(PostProcessError) as exc:
        ContractGenerator().generate("contract", sample_data(), {"party.name", "does.not.exist"})
    assert str(exc.value) == "Expected form fields are missing: [does.not.exist]"


def test_marks_requested_fields_as_required() -> None:
    required = {"party.name", "sig.date", "agree.terms"}
    pdf = ContractGenerator().generate("contract", sample_data(), EXPECTED_FIELDS, required)
    by_name = fields_by_name(pdf)
    for name in required:
        assert int(by_name[name].get("/Ff", 0)) & FF_REQUIRED, f"{name} should be required"
    assert not int(by_name["party.email"].get("/Ff", 0)) & FF_REQUIRED
    assert not int(by_name["sig.name"].get("/Ff", 0)) & FF_REQUIRED


def test_unknown_required_field_fails() -> None:
    with pytest.raises(PostProcessError) as exc:
        ContractGenerator().generate("contract", sample_data(), set(), {"does.not.exist"})
    assert str(exc.value) == "Fields marked required are missing: [does.not.exist]"
