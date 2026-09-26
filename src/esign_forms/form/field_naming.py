"""Conventions and validation for AcroForm field names.

Field names originate from the ``name`` attribute of HTML form controls in the template. To keep
the generated PDF interoperable with signing services such as DocuSign (which match tabs by field
name), names must be stable, unique, and restricted to a safe character set.

Allowed: ASCII letters, digits, dot, underscore and hyphen; must start with a letter. The dot is
permitted so hierarchical names like ``party.name`` can be used.

**DocuSign transform tags.** DocuSign's ``transformPdfFields=true`` option auto-converts an
AcroForm field into a signing tab based on a keyword *contained in* the field name — e.g. a field
whose name contains ``DocusignSignHere`` becomes a *SignHere* (signature) tab. These names already
satisfy the normal convention, so no special exception is needed; use :meth:`FieldNaming.sign_here`
to build one.
"""

from __future__ import annotations

import re
from typing import Final

_VALID: Final = re.compile(r"[A-Za-z][A-Za-z0-9._-]*")


class FieldNaming:
    """Namespace for field-name helpers (not instantiable)."""

    SIGN_HERE_KEYWORD: Final = "DocusignSignHere"
    """DocuSign PDF-transform keyword that converts a form field into a SignHere tab. The field
    name must *contain* this substring; a trailing index keeps names unique."""

    def __init__(self) -> None:
        raise TypeError("FieldNaming is not instantiable")

    @staticmethod
    def is_valid(name: str | None) -> bool:
        return name is not None and _VALID.fullmatch(name) is not None

    @staticmethod
    def sign_here(index: int) -> str:
        """Builds the DocuSign transform field name for a SignHere (signature) tab.

        The ``index`` only keeps multiple signature field names distinct — it does *not* route
        the tab to a particular signer. Converted tabs are all assigned to the document's
        ``assignTabsToRecipientId`` (the first recipient by default).
        """
        if index < 1:
            raise ValueError(f"Index must be >= 1, was {index}")
        return f"{FieldNaming.SIGN_HERE_KEYWORD}{index}"

    @staticmethod
    def require_valid(name: str | None) -> None:
        """Validates a field name, raising :class:`ValueError` if it violates the convention."""
        if not FieldNaming.is_valid(name):
            raise ValueError(
                f"Invalid AcroForm field name '{name}'. Names must start with a letter "
                "and contain only letters, digits, '.', '_' or '-'."
            )
