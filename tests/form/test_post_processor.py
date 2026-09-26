from __future__ import annotations

import pytest

from contract_generator.form import AcroFormPostProcessor, ContractFormReader, PostProcessError
from contract_generator.render import HtmlToPdfRenderer
from tests.conftest import plain_pdf


def _render(body: str) -> bytes:
    return HtmlToPdfRenderer().render(
        f'<html><body style="font-family: ContractFont"><form>{body}</form></body></html>'
    )


def test_pdf_without_acroform_is_rejected() -> None:
    with pytest.raises(PostProcessError, match="PDF has no AcroForm"):
        AcroFormPostProcessor().process(plain_pdf())


def test_invalid_field_name_is_rejected() -> None:
    with pytest.raises(ValueError, match="Invalid AcroForm field name 'bad name'"):
        AcroFormPostProcessor().process(_render('<input type="text" name="bad name" />'))


def test_duplicate_field_name_is_rejected() -> None:
    pdf = _render('<input type="text" name="a.b" /><input type="text" name="a.b" />')
    with pytest.raises(PostProcessError, match="Duplicate AcroForm field name: a.b"):
        AcroFormPostProcessor().process(pdf)


def test_radio_and_select_controls_round_trip() -> None:
    pdf = AcroFormPostProcessor().process(
        _render(
            '<input type="radio" name="plan.tier" value="basic" />'
            '<input type="radio" name="plan.tier" value="pro" />'
            '<select name="plan.term"><option value="m">Monthly</option>'
            '<option value="y" selected="selected">Yearly</option></select>'
        ),
        expected_field_names={"plan.tier", "plan.term"},
        required_field_names={"plan.tier"},
    )
    values = ContractFormReader().read(pdf)
    assert values == {"plan.tier": "", "plan.term": "y"}


def test_garbage_bytes_raise_post_process_error() -> None:
    with pytest.raises(PostProcessError):
        AcroFormPostProcessor().process(b"not a pdf")
