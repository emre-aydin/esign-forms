"""Public entry point for generating contract PDFs and reading their filled values."""

from __future__ import annotations

import os
from collections.abc import Mapping, Set
from typing import BinaryIO

from contract_generator.form.post_processor import AcroFormPostProcessor
from contract_generator.form.reader import ContractFormReader
from contract_generator.model import ContractData
from contract_generator.render import HtmlToPdfRenderer
from contract_generator.template import ContractTemplateEngine


class ContractGenerator:
    """Turns a contract template plus data into a DocuSign-ready PDF whose fillable regions are
    interactive AcroForm fields, and reads back the values a user has filled into such a PDF.

    Generate pipeline: ``Jinja2 -> HTML -> WeasyPrint (form controls) -> pypdf normalize``.
    Read pipeline (inverse): ``PDF -> pypdf AcroForm -> field name/value dict``.

    >>> pdf = ContractGenerator().generate("contract", data)          # doctest: +SKIP
    >>> filled = ContractGenerator().read_values(filled_pdf_bytes)    # doctest: +SKIP
    """

    def __init__(
        self,
        template_engine: ContractTemplateEngine | None = None,
        renderer: HtmlToPdfRenderer | None = None,
        post_processor: AcroFormPostProcessor | None = None,
        form_reader: ContractFormReader | None = None,
    ) -> None:
        self._template_engine = template_engine or ContractTemplateEngine()
        self._renderer = renderer or HtmlToPdfRenderer()
        self._post_processor = post_processor or AcroFormPostProcessor()
        self._form_reader = form_reader or ContractFormReader()

    def generate(
        self,
        template_name: str,
        data: ContractData | Mapping[str, object],
        expected_field_names: Set[str] = frozenset(),
        required_field_names: Set[str] = frozenset(),
    ) -> bytes:
        """Generates the contract PDF.

        :param template_name: template name under ``resources/templates/`` (without ``.html``)
        :param data: dynamic contract content
        :param expected_field_names: field names that must exist in the output
        :param required_field_names: field names to mark as required (AcroForm Required flag);
            with DocuSign ``transformPdfFields=true`` they become required tabs. Must be present
            in the template.
        """
        contract_data = data if isinstance(data, ContractData) else ContractData(data)
        html = self._template_engine.render(template_name, contract_data)
        pdf = self._renderer.render(html, None)
        return self._post_processor.process(pdf, expected_field_names, required_field_names)

    def read_values(self, source: bytes | str | os.PathLike[str] | BinaryIO) -> dict[str, str]:
        """Reads the current AcroForm field values from PDF bytes, a path, or a binary stream.

        Returns an empty dict if the PDF has no AcroForm. A stream is not closed.
        """
        return self._form_reader.read(source)
