def require_text(value: str | None, field: str) -> None:
    if value is None or not value.strip():
        raise ValueError(f"{field} must not be blank")
