import pytest

from contract_generator import ContractData


def test_builder_snapshots_values_and_view_is_read_only() -> None:
    builder = ContractData.builder().put("a", 1)
    data = builder.build()
    builder.put("b", 2)
    assert dict(data.as_map()) == {"a": 1}
    with pytest.raises(TypeError):
        data.as_map()["a"] = 3  # type: ignore[index]


def test_none_key_is_rejected() -> None:
    with pytest.raises(TypeError):
        ContractData.builder().put(None, 1)  # type: ignore[arg-type]


def test_empty() -> None:
    assert dict(ContractData.empty().as_map()) == {}
