"""Renders an HTML string to PDF bytes with interactive AcroForm fields using WeasyPrint."""

from __future__ import annotations

from importlib import resources
from typing import Final


class RenderError(RuntimeError):
    """Raised when the underlying renderer fails."""


FONT_FAMILY: Final = "ContractFont"
"""CSS font-family name under which the bundled font is registered; templates should use it."""

_FONT_RESOURCE: Final = "resources/fonts/Contract-Regular.ttf"


class HtmlToPdfRenderer:
    """Renders HTML to PDF with WeasyPrint's ``pdf_forms`` enabled.

    Native HTML form controls (``<input>``, ``<textarea>``, ``<select>``, checkbox/radio) are
    emitted as interactive AcroForm fields rather than being flattened. Each control's ``name``
    attribute becomes the AcroForm field's fully-qualified name.
    """

    FONT_FAMILY: Final = FONT_FAMILY

    def render(self, html: str, base_url: str | None = None) -> bytes:
        """Renders ``html`` to PDF; ``base_url`` resolves relative resources (may be ``None``)."""
        try:
            from weasyprint import CSS, HTML
            from weasyprint.text.fonts import FontConfiguration
        except OSError as e:  # WeasyPrint raises OSError when Pango/GLib can't be loaded
            raise RenderError("WeasyPrint system libraries (Pango) are not available") from e

        font_file = resources.files("contract_generator").joinpath(_FONT_RESOURCE)
        if not font_file.is_file():
            raise RenderError(f"Bundled font not found in package: {_FONT_RESOURCE}")

        try:
            with resources.as_file(font_file) as font_path:
                font_config = FontConfiguration()
                font_css = CSS(
                    string=(
                        f'@font-face {{ font-family: "{FONT_FAMILY}"; '
                        f'src: url("{font_path.as_uri()}"); }}'
                    ),
                    font_config=font_config,
                )
                pdf = HTML(string=html, base_url=base_url).write_pdf(
                    stylesheets=[font_css], font_config=font_config, pdf_forms=True
                )
        except Exception as e:
            raise RenderError("Failed to render HTML to PDF") from e
        if pdf is None:
            raise RenderError("Failed to render HTML to PDF")
        return bytes(pdf)
