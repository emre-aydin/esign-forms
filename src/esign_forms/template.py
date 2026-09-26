"""Renders a Jinja2 HTML template (a file path or template text) to an HTML string."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from jinja2 import BaseLoader, Environment, FileSystemLoader

from esign_forms.model import FormData

type TemplateSource = str | os.PathLike[str]
"""A template file path (``Path``/``PathLike``) or the template text itself (``str``)."""


@dataclass(frozen=True)
class RenderedTemplate:
    html: str
    base_url: str | None
    """Directory URL that relative resources (CSS, images) resolve against; ``None`` for text."""


class TemplateEngine:
    """Renders templates with Jinja2.

    A ``Path`` (or other ``os.PathLike``) is loaded from disk, with ``{% include %}`` /
    ``{% extends %}`` resolved relative to the file's directory. A plain ``str`` is treated as the
    template text. Autoescaping is always on, and undefined variables render as empty strings.
    """

    def render(self, template: TemplateSource, data: FormData) -> RenderedTemplate:
        context = dict(data.as_map())
        if isinstance(template, str):
            return RenderedTemplate(
                self._env(BaseLoader()).from_string(template).render(context), None
            )
        path = Path(template).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Template not found: {path}")
        env = self._env(FileSystemLoader(path.parent))
        html = env.get_template(path.name).render(context)
        return RenderedTemplate(html, path.parent.as_uri() + "/")

    @staticmethod
    def _env(loader: BaseLoader) -> Environment:
        return Environment(loader=loader, autoescape=True, keep_trailing_newline=True)
