"""Entry point of the worker (``contract-generator-worker`` console script)."""

from __future__ import annotations

import asyncio
import os
import signal
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor

from temporalio.client import Client
from temporalio.runtime import PrometheusConfig, Runtime, TelemetryConfig
from temporalio.service import TLSConfig
from temporalio.worker import Worker

from contract_generator.temporal.activities import ContractActivities
from contract_generator.temporal.config import TemporalWorkerConfig
from contract_generator.temporal.workflow import WORKFLOW_RUNNER, ContractSigningWorkflow

_ACTIVITY_THREADS = 8


def _runtime(env: Mapping[str, str]) -> Runtime | None:
    port = env.get("TEMPORAL_PROMETHEUS_PORT")
    if port is None or not port.strip():
        return None
    runtime = Runtime(
        telemetry=TelemetryConfig(
            metrics=PrometheusConfig(bind_address=f"0.0.0.0:{int(port.strip())}")
        )
    )
    print(f"Prometheus metrics available on :{port.strip()}/metrics", flush=True)
    return runtime


async def run(env: Mapping[str, str]) -> None:
    config = TemporalWorkerConfig.from_env(env)
    tls: TLSConfig | bool = False
    if config.uses_tls and config.tls_root_ca_pem is not None:
        tls = TLSConfig(server_root_ca_cert=config.tls_root_ca_pem.encode("utf-8"))
    client = await Client.connect(
        config.target, namespace=config.namespace, tls=tls, runtime=_runtime(env)
    )

    activities = ContractActivities()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    with ThreadPoolExecutor(max_workers=_ACTIVITY_THREADS) as executor:
        worker = Worker(
            client,
            task_queue=config.task_queue,
            workflows=[ContractSigningWorkflow],
            workflow_runner=WORKFLOW_RUNNER,
            activities=[activities.generate_pdf, activities.send_to_docusign],
            activity_executor=executor,
        )
        print(
            f"Starting contract-generator worker: target={config.target} "
            f"namespace={config.namespace} queue={config.task_queue} tls={config.uses_tls}",
            flush=True,
        )
        async with worker:
            await stop.wait()


def main() -> None:
    asyncio.run(run(os.environ))


if __name__ == "__main__":
    main()
