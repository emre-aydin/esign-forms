import pytest

from contract_generator.temporal import TemporalWorkerConfig


def test_reads_all_values_from_env() -> None:
    config = TemporalWorkerConfig.from_env(
        {
            "TEMPORAL_HOST": "temporal.example:7233",
            "TEMPORAL_NAMESPACE": "prod",
            "TEMPORAL_QUEUE": "contracts",
            "TEMPORAL_TLS_ROOT_CAS": "-----BEGIN CERTIFICATE-----\nabc\n-----END CERTIFICATE-----",
        }
    )
    assert config.target == "temporal.example:7233"
    assert config.namespace == "prod"
    assert config.task_queue == "contracts"
    assert config.uses_tls


def test_applies_defaults_for_host_and_namespace() -> None:
    config = TemporalWorkerConfig.from_env({"TEMPORAL_QUEUE": "contracts"})
    assert config.target == "localhost:7233"
    assert config.namespace == "default"
    assert config.tls_root_ca_pem is None
    assert not config.uses_tls


def test_requires_queue() -> None:
    with pytest.raises(ValueError, match="TEMPORAL_QUEUE must be set"):
        TemporalWorkerConfig.from_env({"TEMPORAL_HOST": "temporal.example:7233"})


def test_blank_tls_is_treated_as_no_tls() -> None:
    config = TemporalWorkerConfig.from_env(
        {"TEMPORAL_QUEUE": "contracts", "TEMPORAL_TLS_ROOT_CAS": "   "}
    )
    assert not config.uses_tls
    assert config.tls_root_ca_pem is None
