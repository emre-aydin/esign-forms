from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor

from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from contract_generator.temporal import (
    ContractSigningRequest,
    ContractSigningWorkflow,
    SignerInfo,
)
from contract_generator.temporal.workflow import WORKFLOW_RUNNER

TASK_QUEUE = "test-contracts"
CANNED_PDF = bytes([1, 2, 3, 4])


async def test_generates_then_sends_and_returns_envelope_id() -> None:
    calls: list[str] = []
    generate_requests: list[ContractSigningRequest] = []
    pdf_seen_by_send: list[bytes] = []

    @activity.defn(name="generate_pdf")
    def generate_pdf(request: ContractSigningRequest) -> bytes:
        calls.append("generate")
        generate_requests.append(request)
        return CANNED_PDF

    @activity.defn(name="send_to_docusign")
    def send_to_docusign(pdf: bytes, request: ContractSigningRequest) -> str:
        calls.append("send")
        pdf_seen_by_send.append(pdf)
        return "envelope-123"

    request = ContractSigningRequest(
        template_name="contract",
        parameters={"partyName": "Acme"},
        expected_field_names=frozenset({"signatureField"}),
        required_field_names=frozenset({"signatureField"}),
        document_name="Consulting Agreement",
        email_subject="Please sign",
        signers=(SignerInfo("Jane Doe", "jane@example.com"),),
    )

    async with await WorkflowEnvironment.start_time_skipping() as env:
        with ThreadPoolExecutor() as executor:
            async with Worker(
                env.client,
                task_queue=TASK_QUEUE,
                workflows=[ContractSigningWorkflow],
                workflow_runner=WORKFLOW_RUNNER,
                activities=[generate_pdf, send_to_docusign],
                activity_executor=executor,
            ):
                envelope_id = await env.client.execute_workflow(
                    ContractSigningWorkflow.generate_and_send,
                    request,
                    id=f"wf-{uuid.uuid4()}",
                    task_queue=TASK_QUEUE,
                )

    assert envelope_id == "envelope-123"
    assert calls == ["generate", "send"]
    assert generate_requests[0] == request, "request survives the JSON round trip"
    assert pdf_seen_by_send == [CANNED_PDF]
