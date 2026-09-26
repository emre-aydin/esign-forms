"""Temporal worker that generates fillable PDFs and sends them to DocuSign.

Requires the optional ``worker`` extra: ``pip install 'esign-forms[worker]'``.
"""

try:
    import temporalio  # noqa: F401
except ImportError as e:  # pragma: no cover - exercised only without the extra
    raise ImportError(
        "esign_forms.temporal requires the 'worker' extra: pip install 'esign-forms[worker]'"
    ) from e

from esign_forms.temporal.activities import FormActivities
from esign_forms.temporal.config import TemporalWorkerConfig
from esign_forms.temporal.dto import FormSigningRequest, SignerInfo
from esign_forms.temporal.workflow import FormSigningWorkflow

__all__ = [
    "FormActivities",
    "FormSigningRequest",
    "FormSigningWorkflow",
    "SignerInfo",
    "TemporalWorkerConfig",
]
