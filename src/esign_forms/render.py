"""Renders an HTML string to PDF bytes with interactive AcroForm fields using WeasyPrint."""

from __future__ import annotations

import os
import sys
from importlib import resources
from pathlib import Path
from typing import Final


class RenderError(RuntimeError):
    """Raised when the underlying renderer fails."""


FONT_FAMILY: Final = "EsignFormsFont"
"""CSS font-family name under which the bundled font is registered; templates should use it."""

_FONT_RESOURCE: Final = "resources/fonts/OpenSans-Regular.ttf"

_MACOS_LIBRARY_DIRS: Final = ("/opt/homebrew/lib", "/usr/local/lib")


def _ensure_macos_library_path() -> None:
    """Lets WeasyPrint find Homebrew's Pango/GLib on macOS.

    WeasyPrint locates them with ``ctypes.util.find_library``, which reads
    ``DYLD_FALLBACK_LIBRARY_PATH`` at lookup time. That variable is usually unset (macOS strips
    ``DYLD_*`` across ``uv run`` and many launchers), so default it to the Homebrew lib dir
    before WeasyPrint is first imported. An explicitly set value is left untouched.
    """
    if sys.platform != "darwin" or os.environ.get("DYLD_FALLBACK_LIBRARY_PATH"):
        return
    for lib_dir in _MACOS_LIBRARY_DIRS:
        if Path(lib_dir, "libpango-1.0.dylib").exists():
            os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = lib_dir
            return


class HtmlToPdfRenderer:
    """Renders HTML to PDF with WeasyPrint's ``pdf_forms`` enabled.

    Native HTML form controls (``<input>``, ``<textarea>``, ``<select>``, checkbox/radio) are
    emitted as interactive AcroForm fields rather than being flattened. Each control's ``name``
    attribute becomes the AcroForm field's fully-qualified name.
    """

    FONT_FAMILY: Final = FONT_FAMILY

    def render(self, html: str, base_url: str | None = None) -> bytes:
        """Renders ``html`` to PDF; ``base_url`` resolves relative resources (may be ``None``)."""
        _ensure_macos_library_path()
        try:
            from weasyprint import CSS, HTML
            from weasyprint.text.fonts import FontConfiguration
        except OSError as e:  # WeasyPrint raises OSError when Pango/GLib can't be loaded
            raise RenderError(
                "WeasyPrint system libraries (Pango) are not available. Install them: "
                "`brew install pango` (macOS) or `apt-get install libpango-1.0-0 "
                "libpangoft2-1.0-0 libharfbuzz-subset0` (Debian/Ubuntu)."
            ) from e

        font_file = resources.files("esign_forms").joinpath(_FONT_RESOURCE)
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
