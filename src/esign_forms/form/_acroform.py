"""Low-level helpers for walking a PDF AcroForm field tree with pypdf."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import cast

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, NameObject

FF_REQUIRED = 1 << 1
FF_RADIO = 1 << 15
FF_PUSHBUTTON = 1 << 16


@dataclass(frozen=True)
class FieldNode:
    """A field in the AcroForm tree together with its fully-qualified name."""

    name: str
    field: DictionaryObject
    terminal: bool


def acroform_of(pdf: PdfReader | PdfWriter) -> DictionaryObject | None:
    """Returns the catalog's ``/AcroForm`` dictionary, or ``None`` when absent/empty."""
    root = cast(
        DictionaryObject,
        pdf.root_object if isinstance(pdf, PdfWriter) else pdf.trailer["/Root"].get_object(),
    )
    form = root.get("/AcroForm")
    if form is None:
        return None
    form = form.get_object()
    if not isinstance(form, DictionaryObject) or "/Fields" not in form:
        return None
    return form


def _field_kids(field: DictionaryObject) -> list[DictionaryObject]:
    """Kids that are themselves fields (have a partial name); pure widget kids are excluded."""
    kids = field.get("/Kids")
    if kids is None:
        return []
    result = []
    for kid in kids.get_object():
        kid = kid.get_object()
        if isinstance(kid, DictionaryObject) and "/T" in kid:
            result.append(kid)
    return result


def walk_fields(form: DictionaryObject) -> Iterator[FieldNode]:
    """Depth-first pre-order walk of the field tree, yielding every field (terminal or not)."""

    def visit(field: DictionaryObject, prefix: str | None) -> Iterator[FieldNode]:
        partial = str(field.get("/T", ""))
        name = partial if prefix is None else f"{prefix}.{partial}"
        kids = _field_kids(field)
        yield FieldNode(name, field, terminal=not kids)
        for kid in kids:
            yield from visit(kid, name)

    for entry in cast(ArrayObject, form["/Fields"].get_object()):
        field = entry.get_object()
        if isinstance(field, DictionaryObject):
            yield from visit(field, None)


def inherited(field: DictionaryObject, key: str) -> object | None:
    """Looks up an inheritable field attribute (``/FT``, ``/Ff``, ``/V``) up the parent chain."""
    node: DictionaryObject | None = field
    while node is not None:
        if key in node:
            return node[key].get_object()
        parent = node.get("/Parent")
        node = parent.get_object() if parent is not None else None
    return None


def widgets_of(field: DictionaryObject) -> list[DictionaryObject]:
    """Widget annotations of a terminal field: the field itself (merged) or its widget kids."""
    kids = field.get("/Kids")
    if kids is None:
        return [field]
    return [k.get_object() for k in kids.get_object()]


def on_states(field: DictionaryObject) -> list[str]:
    """Names of the non-``Off`` normal appearance states across a button field's widgets."""
    states: list[str] = []
    for widget in widgets_of(field):
        ap = widget.get("/AP")
        if ap is None:
            continue
        normal = ap.get_object().get("/N")
        if normal is None:
            continue
        normal = normal.get_object()
        if isinstance(normal, DictionaryObject):
            states.extend(str(k) for k in normal if k != "/Off")
    return states


def set_kids(node: DictionaryObject, kids: list[DictionaryObject]) -> None:
    node[NameObject("/Kids")] = ArrayObject(kids)
