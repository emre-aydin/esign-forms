"""Validates and normalizes the AcroForm produced by WeasyPrint."""

from __future__ import annotations

import io
from collections.abc import Iterable, Set
from typing import cast

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PyPdfError
from pypdf.generic import (
    ArrayObject,
    BooleanObject,
    DictionaryObject,
    IndirectObject,
    NameObject,
    NumberObject,
    TextStringObject,
)

from esign_forms.form._acroform import FF_REQUIRED, acroform_of, walk_fields
from esign_forms.form.field_naming import FieldNaming


class PostProcessError(RuntimeError):
    """Raised when the AcroForm is missing, malformed, or fails validation."""


def _format_names(names: Iterable[str]) -> str:
    return "[" + ", ".join(sorted(names)) + "]"


class AcroFormPostProcessor:
    """Makes the rendered PDF ready to hand off to a signing service.

    Responsibilities:

    * Normalize WeasyPrint's flat field list into a spec-compliant tree: dotted names such as
      ``party.name`` become a non-terminal ``party`` field with a terminal ``name`` kid, and radio
      widgets are listed only under their group.
    * Enforce the :class:`FieldNaming` convention and reject duplicate field names.
    * Set ``NeedAppearances = true`` so viewers/signing services regenerate the visual appearance
      of values typed into the fields.
    * Optionally assert that an expected set of fields is present.
    * Optionally mark specific fields as required (AcroForm Required flag). When the PDF is later
      sent to DocuSign with ``transformPdfFields=true``, this flag carries over to the
      auto-converted tab's required attribute.
    """

    def process(
        self,
        pdf_bytes: bytes,
        expected_field_names: Set[str] = frozenset(),
        required_field_names: Set[str] = frozenset(),
    ) -> bytes:
        try:
            writer = PdfWriter(clone_from=PdfReader(io.BytesIO(pdf_bytes)))
        except (PyPdfError, OSError, ValueError) as e:
            raise PostProcessError("Failed to post-process AcroForm") from e

        form = acroform_of(writer)
        if form is None or not form["/Fields"]:
            raise PostProcessError(
                "PDF has no AcroForm; the template must contain named HTML form controls."
            )

        _build_hierarchy(writer, form)
        form[NameObject("/NeedAppearances")] = BooleanObject(True)

        by_name: dict[str, DictionaryObject] = {}
        for node in walk_fields(form):
            FieldNaming.require_valid(node.name)
            if node.name in by_name:
                raise PostProcessError(f"Duplicate AcroForm field name: {node.name}")
            by_name[node.name] = node.field

        if expected_field_names:
            missing = set(expected_field_names) - by_name.keys()
            if missing:
                raise PostProcessError(
                    f"Expected form fields are missing: {_format_names(missing)}"
                )

        if required_field_names:
            missing = set(required_field_names) - by_name.keys()
            if missing:
                raise PostProcessError(
                    f"Fields marked required are missing: {_format_names(missing)}"
                )
            for name in required_field_names:
                field = by_name[name]
                flags = int(field.get("/Ff", 0))
                field[NameObject("/Ff")] = NumberObject(flags | FF_REQUIRED)

        out = io.BytesIO()
        writer.write(out)
        return out.getvalue()


def _build_hierarchy(writer: PdfWriter, form: DictionaryObject) -> None:
    """Rebuilds ``/Fields`` so dotted names form a field tree.

    WeasyPrint writes every control as a root field whose ``/T`` is the full dotted name, and it
    also lists radio-group widgets as root entries alongside their group. Radio widgets get their
    field-level keys stripped (they inherit them from the group) and only true root fields are
    kept; each dotted root is then re-parented under (possibly newly created) non-terminal fields.
    """
    roots: list[IndirectObject] = []
    for ref in cast(ArrayObject, form["/Fields"]):
        field = cast(DictionaryObject, ref.get_object())
        if "/Parent" in field:
            continue
        for kid in cast(ArrayObject, field.get("/Kids", ArrayObject())):
            widget = cast(DictionaryObject, kid.get_object())
            for key in ("/T", "/TU", "/FT"):
                widget.pop(NameObject(key), None)
        roots.append(ref)

    new_roots: list[IndirectObject] = []
    parents: dict[str, IndirectObject] = {}

    def parent_for(path: list[str]) -> IndirectObject:
        key = ".".join(path)
        if key in parents:
            return parents[key]
        node = DictionaryObject(
            {
                NameObject("/T"): TextStringObject(path[-1]),
                NameObject("/Kids"): ArrayObject(),
            }
        )
        # pypdf has no public API for registering a new indirect object on a writer.
        ref = writer._add_object(node)
        if len(path) == 1:
            new_roots.append(ref)
        else:
            grandparent = parent_for(path[:-1])
            node[NameObject("/Parent")] = grandparent
            _kids(grandparent).append(ref)
        parents[key] = ref
        return ref

    for ref in roots:
        field = cast(DictionaryObject, ref.get_object())
        parts = str(field.get("/T", "")).split(".")
        if len(parts) == 1:
            new_roots.append(ref)
            continue
        parent = parent_for(parts[:-1])
        field[NameObject("/T")] = TextStringObject(parts[-1])
        field[NameObject("/Parent")] = parent
        _kids(parent).append(ref)

    form[NameObject("/Fields")] = ArrayObject(new_roots)


def _kids(ref: IndirectObject) -> ArrayObject:
    return cast(ArrayObject, cast(DictionaryObject, ref.get_object())["/Kids"])
