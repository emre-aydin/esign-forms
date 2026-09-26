#!/bin/bash
# Entry point for the temporal-worker-k8s charm's Pebble service.
#
# The charm injects the Temporal connection settings (TEMPORAL_HOST, TEMPORAL_NAMESPACE,
# TEMPORAL_QUEUE, TEMPORAL_TLS_ROOT_CAS, TEMPORAL_PROMETHEUS_PORT) and any extra environment
# (e.g. DOCUSIGN_* secrets) into this container's environment before starting the service.
set -euo pipefail

exec /app/venv/bin/contract-generator-worker
