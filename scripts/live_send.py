"""Manually sends ``examples/contract.html`` to DocuSign demo and prints the envelope id.

Reads ``DOCUSIGN_ACCOUNT_ID``, ``DOCUSIGN_INTEGRATION_KEY``, ``DOCUSIGN_USER_ID``, ``SIGNER_NAME``
and ``SIGNER_EMAIL`` from the environment, and the RSA key from ``private_key.pem`` next to
this script.
Run from anywhere: ``uv run python scripts/live_send.py``.
"""

from __future__ import annotations

import os
from pathlib import Path

from esign_forms import FormData, FormGenerator
from esign_forms.docusign import DocuSignConfig, DocuSignSender, SendRequest, Signer

_HERE = Path(__file__).resolve().parent


def main() -> None:
    config = DocuSignConfig(
        account_id=os.environ["DOCUSIGN_ACCOUNT_ID"],
        # OAuth host: demo; use "account.docusign.com" for production.
        oauth_base_path="account-d.docusign.com",
        integration_key=os.environ["DOCUSIGN_INTEGRATION_KEY"],
        user_id=os.environ["DOCUSIGN_USER_ID"],
        private_key=(_HERE / "private_key.pem").read_bytes(),
    )
    pdf = FormGenerator().generate(
        _HERE.parent / "examples" / "contract.html",
        FormData.empty(),
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
