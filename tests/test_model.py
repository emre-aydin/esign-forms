import pytest

from esign_forms import FormData


def test_builder_snapshots_values_and_view_is_read_only() -> None:
    builder = FormData.builder().put("a", 1)
    data = builder.build()
    builder.put("b", 2)
    assert dict(data.as_map()) == {"a": 1}
    with pytest.raises(TypeError):
        data.as_map()["a"] = 3  # type: ignore[index]


def test_none_key_is_rejected() -> None:
    with pytest.raises(TypeError):
        FormData.builder().put(None, 1)  # type: ignore[arg-type]


def test_empty() -> None:
    assert dict(FormData.empty().as_map()) == {}
