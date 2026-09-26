from __future__ import annotations

from pathlib import Path

import pytest

from esign_forms.docusign import DocuSignConfig

BASE_ENV = {
    "DOCUSIGN_ACCOUNT_ID": "acct",
    "DOCUSIGN_OAUTH_BASE_PATH": "account-d.docusign.com",
    "DOCUSIGN_INTEGRATION_KEY": "ik",
    "DOCUSIGN_USER_ID": "user",
}


def test_from_env_reads_key_from_path(tmp_path: Path) -> None:
    key = tmp_path / "key.pem"
    key.write_bytes(b"PEM")
    config = DocuSignConfig.from_env({**BASE_ENV, "DOCUSIGN_PRIVATE_KEY_PATH": str(key)})
    assert config == DocuSignConfig("acct", "account-d.docusign.com", "ik", "user", b"PEM")


def test_from_env_prefers_inline_key(tmp_path: Path) -> None:
    config = DocuSignConfig.from_env(
        {**BASE_ENV, "DOCUSIGN_PRIVATE_KEY": "INLINE", "DOCUSIGN_PRIVATE_KEY_PATH": "/nope"}
    )
    assert config.private_key == b"INLINE"


def test_from_env_errors() -> None:
    with pytest.raises(ValueError, match="DOCUSIGN_PRIVATE_KEY or DOCUSIGN_PRIVATE_KEY_PATH"):
        DocuSignConfig.from_env(BASE_ENV)
    with pytest.raises(ValueError, match="Failed to read DOCUSIGN_PRIVATE_KEY_PATH"):
        DocuSignConfig.from_env({**BASE_ENV, "DOCUSIGN_PRIVATE_KEY_PATH": "/does/not/exist"})
    with pytest.raises(ValueError, match="account_id"):
        DocuSignConfig.from_env({"DOCUSIGN_PRIVATE_KEY": "x"})
