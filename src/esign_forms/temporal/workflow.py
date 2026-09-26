from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner, SandboxRestrictions

with workflow.unsafe.imports_passed_through():
    from esign_forms.temporal.activities import FormActivities
    from esign_forms.temporal.dto import FormSigningRequest

# Importing this module inside the sandbox also runs the parent packages' __init__, which pull in
# the PDF/DocuSign stack. None of it is used by workflow code, so pass it through un-sandboxed.
WORKFLOW_RUNNER = SandboxedWorkflowRunner(
    restrictions=SandboxRestrictions.default.with_passthrough_modules(
        "pypdf",
        "jinja2",
        "weasyprint",
        "docusign_esign",
        "urllib3",
        "esign_forms.generator",
        "esign_forms.model",
        "esign_forms.template",
        "esign_forms.render",
        "esign_forms.form",
        "esign_forms.docusign",
        "esign_forms.temporal.activities",
        "esign_forms.temporal.config",
        "esign_forms.temporal.dto",
    )
)

_START_TO_CLOSE = timedelta(minutes=2)
_RETRY = RetryPolicy(maximum_attempts=3)


@workflow.defn(name="FormSigningWorkflow")
class FormSigningWorkflow:
    """Generates the PDF, then sends it to DocuSign; returns the envelope id.

    The PDF bytes travel between the two activities through workflow history, which is fine
    under Temporal's ~2 MB payload limit.
    """

    @workflow.run
    async def generate_and_send(self, request: FormSigningRequest) -> str:
        pdf = await workflow.execute_activity_method(
            FormActivities.generate_pdf,
            request,
            start_to_close_timeout=_START_TO_CLOSE,
            retry_policy=_RETRY,
        )
        return await workflow.execute_activity_method(
            FormActivities.send_to_docusign,
            args=[pdf, request],
            start_to_close_timeout=_START_TO_CLOSE,
            retry_policy=_RETRY,
        )
