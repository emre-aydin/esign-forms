"""Manually sends the bundled contract to DocuSign demo for signature and prints the envelope id.

Reads ``INTEGRATION_KEY`` from the environment and the RSA key from ``./private_key.pem``.
Run from the repo root: ``uv run python scripts/live_send.py``.
"""

from __future__ import annotations

import os
from pathlib import Path

from contract_generator import ContractData, ContractGenerator
from contract_generator.docusign import DocuSignConfig, DocuSignSender, SendRequest, Signer


def main() -> None:
    config = DocuSignConfig(
        account_id=os.environ["DOCUSIGN_ACCOUNT_ID"],
        # OAuth host: demo; use "account.docusign.com" for production.
        oauth_base_path="account-d.docusign.com",
        integration_key=os.environ["DOCUSIGN_INTEGRATION_KEY"],
        user_id=os.environ["DOCUSIGN_USER_ID"],
        private_key=Path("private_key.pem").read_bytes(),
    )
    pdf = ContractGenerator().generate(
        "contract",
        ContractData.empty(),
        {"party.name", "party.email", "sig.name", "sig.date"},  # expected fields
        {"party.name", "sig.name", "sig.date"},  # required fields
    )
    envelope_id = DocuSignSender.for_live_docusign(config).send_for_signature(
        SendRequest(
            "Consulting Services Agreement",
            pdf,
            "Please sign: Consulting Services Agreement",
            [Signer(os.environ["SIGNER_NAME"], os.environ["SIGNER_EMAIL"])],
        )
    )
    print(envelope_id)


if __name__ == "__main__":
    main()
