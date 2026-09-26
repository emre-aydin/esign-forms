"""Reads the current values of AcroForm fields from a PDF."""

from __future__ import annotations

import io
import os
from pathlib import Path
from typing import BinaryIO

from pypdf import PdfReader
from pypdf.errors import PyPdfError
from pypdf.generic import ArrayObject, DictionaryObject, NameObject

from contract_generator.form._acroform import (
    FF_PUSHBUTTON,
    FF_RADIO,
    acroform_of,
    inherited,
    on_states,
    walk_fields,
)


class ReadError(RuntimeError):
    """Raised when the PDF cannot be loaded or its AcroForm cannot be read."""


class ContractFormReader:
    """Reads AcroForm field values from a PDF, keyed by fully-qualified field name.

    This is the inverse of the generate pipeline: :class:`~contract_generator.ContractGenerator`
    produces a PDF whose fillable regions are named AcroForm fields (e.g. ``party.name``,
    ``sig.date``, ``agree.terms``); this reader extracts whatever values a user has since typed
    or selected into those fields.

    Value conventions:

    * Text / textarea / choice fields: the value as typed, or ``""`` if unfilled (multi-select
      choices render as ``"[a, b]"``).
    * Checkboxes: normalized to ``"true"`` / ``"false"``.
    * Radio buttons: the selected option's export value, or ``""`` if none selected.

    Non-terminal fields (parent nodes created by dotted names, e.g. ``party`` for ``party.name``)
    are skipped; only terminal fields are returned. A PDF with no AcroForm at all yields an empty
    dict rather than raising.
    """

    def read(self, source: bytes | str | os.PathLike[str] | BinaryIO) -> dict[str, str]:
        """Reads field values from PDF bytes, a file path (``str``/``Path``), or a binary stream.

        A stream is fully consumed but not closed; the caller owns its lifecycle.
        """
        if isinstance(source, bytes | bytearray):
            stream: BinaryIO = io.BytesIO(source)
            what = "PDF bytes"
        elif isinstance(source, str | os.PathLike):
            path = Path(source)
            try:
                data = path.read_bytes()
            except OSError as e:
                raise ReadError(f"Failed to read AcroForm values from {path}") from e
            stream = io.BytesIO(data)
            what = str(path)
        else:
            stream = source
            what = "PDF stream"
        try:
            return self._read_values(PdfReader(stream))
        except (PyPdfError, OSError, ValueError, KeyError, TypeError) as e:
            raise ReadError(f"Failed to read AcroForm values from {what}") from e

    def _read_values(self, pdf: PdfReader) -> dict[str, str]:
        form = acroform_of(pdf)
        if form is None:
            return {}
        return {node.name: _value_of(node.field) for node in walk_fields(form) if node.terminal}


def _value_of(field: DictionaryObject) -> str:
    field_type = inherited(field, "/FT")
    raw = inherited(field, "/V")
    if field_type == "/Btn":
        flags = int(inherited(field, "/Ff") or 0)  # type: ignore[call-overload]
        if flags & FF_PUSHBUTTON:
            return ""
        if flags & FF_RADIO:
            return _radio_value(field, raw)
        return "true" if _is_checked(field, raw) else "false"
    if isinstance(raw, ArrayObject):
        return "[" + ", ".join(str(v) for v in raw) + "]"
    if isinstance(raw, str):
        return str(raw)
    return ""


def _is_checked(field: DictionaryObject, raw: object) -> bool:
    """A checkbox is checked iff its raw ``/V`` name equals one of its on-appearance states.

    Comparing the raw COS name (rather than trusting ``/Opt`` export-value lookups) is robust to
    producers that write placeholder ``/Opt`` arrays, as openhtmltopdf did.
    """
    return isinstance(raw, NameObject) and str(raw) in on_states(field)


def _radio_value(field: DictionaryObject, raw: object) -> str:
    if not isinstance(raw, NameObject) or raw == "/Off":
        return ""
    state = str(raw)[1:]
    options = inherited(field, "/Opt")
    # WeasyPrint names radio on-states by index ("/0", "/1") into /Opt, which holds the
    # export values from the HTML ``value`` attributes.
    if isinstance(options, ArrayObject) and state.isdigit() and int(state) < len(options):
        return str(options[int(state)].get_object())
    return state
