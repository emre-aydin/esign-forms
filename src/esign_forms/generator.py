"""Public entry point for generating fillable PDFs and reading their filled values."""

from __future__ import annotations

import os
from collections.abc import Mapping, Set
from typing import BinaryIO

from esign_forms.form.post_processor import AcroFormPostProcessor
from esign_forms.form.reader import FormReader
from esign_forms.model import FormData
from esign_forms.render import HtmlToPdfRenderer
from esign_forms.template import TemplateEngine, TemplateSource


class FormGenerator:
    """Turns an HTML template plus data into a DocuSign-ready PDF whose fillable regions are
    interactive AcroForm fields, and reads back the values a user has filled into such a PDF.

    Generate pipeline: ``Jinja2 -> HTML -> WeasyPrint (form controls) -> pypdf normalize``.
    Read pipeline (inverse): ``PDF -> pypdf AcroForm -> field name/value dict``.

    >>> pdf = FormGenerator().generate(Path("contract.html"), data)  # doctest: +SKIP
    >>> filled = FormGenerator().read_values(filled_pdf_bytes)    # doctest: +SKIP
    """

    def __init__(
        self,
        template_engine: TemplateEngine | None = None,
        renderer: HtmlToPdfRenderer | None = None,
        post_processor: AcroFormPostProcessor | None = None,
        form_reader: FormReader | None = None,
    ) -> None:
        self._template_engine = template_engine or TemplateEngine()
        self._renderer = renderer or HtmlToPdfRenderer()
        self._post_processor = post_processor or AcroFormPostProcessor()
        self._form_reader = form_reader or FormReader()

    def generate(
        self,
        template: TemplateSource,
        data: FormData | Mapping[str, object],
        expected_field_names: Set[str] = frozenset(),
        required_field_names: Set[str] = frozenset(),
    ) -> bytes:
        """Generates the PDF.

        :param template: a template file path (``Path``/``PathLike``; includes and relative
            resources resolve from its directory) or the template text itself (``str``)
        :param data: dynamic template values
        :param expected_field_names: field names that must exist in the output
        :param required_field_names: field names to mark as required (AcroForm Required flag);
            with DocuSign ``transformPdfFields=true`` they become required tabs. Must be present
            in the template.
        """
        form_data = data if isinstance(data, FormData) else FormData(data)
        rendered = self._template_engine.render(template, form_data)
        pdf = self._renderer.render(rendered.html, rendered.base_url)
        return self._post_processor.process(pdf, expected_field_names, required_field_names)

    def read_values(self, source: bytes | str | os.PathLike[str] | BinaryIO) -> dict[str, str]:
        """Reads the current AcroForm field values from PDF bytes, a path, or a binary stream.

        Returns an empty dict if the PDF has no AcroForm. A stream is not closed.
        """
        return self._form_reader.read(source)
