from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

DEFAULT_HOST: Final = "localhost:7233"
DEFAULT_NAMESPACE: Final = "default"


def _blank(value: str | None) -> bool:
    return value is None or not value.strip()


@dataclass(frozen=True)
class TemporalWorkerConfig:
    """Connection settings injected by the temporal-worker-k8s charm as ``TEMPORAL_*`` env vars."""

    target: str
    namespace: str
    task_queue: str
    tls_root_ca_pem: str | None = None

    def __post_init__(self) -> None:
        if _blank(self.target):
            raise ValueError("target (TEMPORAL_HOST) must not be blank")
        if _blank(self.namespace):
            raise ValueError("namespace (TEMPORAL_NAMESPACE) must not be blank")
        if _blank(self.task_queue):
            raise ValueError("task_queue (TEMPORAL_QUEUE) must not be blank")

    @property
    def uses_tls(self) -> bool:
        return not _blank(self.tls_root_ca_pem)

    @staticmethod
    def from_env(env: Mapping[str, str]) -> TemporalWorkerConfig:
        host = env.get("TEMPORAL_HOST")
        namespace = env.get("TEMPORAL_NAMESPACE")
        queue = env.get("TEMPORAL_QUEUE")
        if queue is None or _blank(queue):
            raise ValueError("TEMPORAL_QUEUE must be set")
        tls = env.get("TEMPORAL_TLS_ROOT_CAS")
        return TemporalWorkerConfig(
            target=DEFAULT_HOST if host is None or _blank(host) else host,
            namespace=DEFAULT_NAMESPACE if namespace is None or _blank(namespace) else namespace,
            task_queue=queue,
            tls_root_ca_pem=None if tls is None or _blank(tls) else tls,
        )
