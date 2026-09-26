"""Sends a real envelope to DocuSign's demo environment using JWT auth.

Skipped unless ``DOCUSIGN_LIVE_TEST=true``. Required environment variables:

* ``DOCUSIGN_ACCOUNT_ID`` — the DocuSign account id (GUID)
* ``DOCUSIGN_INTEGRATION_KEY`` — the JWT integration key (OAuth client id)
* ``DOCUSIGN_USER_ID`` — GUID of the impersonated user (must have granted consent)
* ``DOCUSIGN_PRIVATE_KEY_PATH`` — path to the RSA private key PEM registered for the key
* ``DOCUSIGN_SIGNER_EMAIL``, ``DOCUSIGN_SIGNER_NAME`` — recipient of the test envelope

Optional: ``DOCUSIGN_OAUTH_BASE_PATH`` (defaults to ``account-d.docusign.com``, the demo env).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from esign_forms import FormGenerator
from esign_forms.docusign import DocuSignConfig, DocuSignSender, SendRequest, Signer
from tests.conftest import EXAMPLE_TEMPLATE, sample_data

pytestmark = pytest.mark.skipif(
    os.environ.get("DOCUSIGN_LIVE_TEST") != "true", reason="DOCUSIGN_LIVE_TEST is not 'true'"
)


def _env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value.strip():
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def test_sends_generated_contract_for_signature() -> None:
    config = DocuSignConfig(
        account_id=_env("DOCUSIGN_ACCOUNT_ID"),
        oauth_base_path=os.environ.get("DOCUSIGN_OAUTH_BASE_PATH", "account-d.docusign.com"),
        integration_key=_env("DOCUSIGN_INTEGRATION_KEY"),
        user_id=_env("DOCUSIGN_USER_ID"),
        private_key=Path(_env("DOCUSIGN_PRIVATE_KEY_PATH")).read_bytes(),
    )
    pdf = FormGenerator().generate(
        EXAMPLE_TEMPLATE,
        sample_data(),
        {
            "party.name",
            "party.email",
            "party.notes",
            "agree.terms",
            "sig.name",
            "sig.title",
            "sig.date",
        },
        {"party.name", "party.email", "sig.name", "sig.date"},
    )
    request = SendRequest(
        "Consulting Services Agreement",
        pdf,
        "Please sign: Consulting Services Agreement (esign-forms live test)",
        [Signer(_env("DOCUSIGN_SIGNER_NAME"), _env("DOCUSIGN_SIGNER_EMAIL"))],
    )
    envelope_id = DocuSignSender.for_live_docusign(config).send_for_signature(request)
    assert envelope_id.strip()
    print(f"Created DocuSign envelope: {envelope_id}")
