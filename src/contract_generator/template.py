"""Renders a named Jinja2 contract template to an HTML string."""

from __future__ import annotations

from jinja2 import Environment, PackageLoader

from contract_generator.model import ContractData


class ContractTemplateEngine:
    """Loads ``resources/templates/<name>.html`` from the package and renders it with Jinja2.

    Autoescaping is always on, so template values are HTML-escaped as Thymeleaf's ``th:text``
    did. Undefined variables render as an empty string.
    """

    def __init__(self, environment: Environment | None = None) -> None:
        self._env = environment or Environment(
            loader=PackageLoader("contract_generator", "resources/templates"),
            autoescape=True,
            auto_reload=True,
            keep_trailing_newline=True,
        )

    def render(self, template_name: str, data: ContractData) -> str:
        return self._env.get_template(f"{template_name}.html").render(dict(data.as_map()))
