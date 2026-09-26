"""Immutable holder for the dynamic values rendered into a template."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any


class FormData:
    """Immutable, insertion-ordered mapping of template variable names to values."""

    __slots__ = ("_values",)

    def __init__(self, values: Mapping[str, Any] | None = None) -> None:
        copied: dict[str, Any] = {}
        for key, value in (values or {}).items():
            if key is None:
                raise TypeError("key must not be None")
            copied[key] = value
        self._values = copied

    @staticmethod
    def empty() -> FormData:
        return FormData()

    @staticmethod
    def builder() -> FormData.Builder:
        return FormData.Builder()

    def as_map(self) -> Mapping[str, Any]:
        """Read-only view of the values."""
        return MappingProxyType(self._values)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, FormData) and self._values == other._values

    def __hash__(self) -> int:
        return hash(tuple(self._values.items()))

    def __repr__(self) -> str:
        return f"FormData({self._values!r})"

    class Builder:
        """Fluent builder; ``build()`` snapshots the values, so the builder can be reused."""

        def __init__(self) -> None:
            self._values: dict[str, Any] = {}

        def put(self, key: str, value: Any) -> FormData.Builder:
            if key is None:
                raise TypeError("key must not be None")
            self._values[key] = value
            return self

        def build(self) -> FormData:
            return FormData(self._values)
