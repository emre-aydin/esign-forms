from __future__ import annotations

from typing import Final

from docusign_esign import ApiClient
from docusign_esign.client.api_exception import ApiException, ArgumentException
from urllib3.exceptions import HTTPError

from esign_forms.docusign.config import DocuSignConfig
from esign_forms.docusign.errors import DocuSignError

SCOPES: Final = ("signature", "impersonation")
JWT_LIFETIME_SECONDS: Final = 3600


class JwtAuthenticator:
    """Obtains a JWT Grant access token and resolves the account's REST base path."""

    def __init__(self, config: DocuSignConfig) -> None:
        self._config = config

    def authenticate(self) -> ApiClient:
        """Returns an :class:`ApiClient` authorized for, and pointed at, the configured account."""
        config = self._config
        api_client = ApiClient()
        api_client.set_oauth_host_name(config.oauth_base_path)
        try:
            token = api_client.request_jwt_user_token(
                client_id=config.integration_key,
                user_id=config.user_id,
                oauth_host_name=config.oauth_base_path,
                private_key_bytes=config.private_key,
                expires_in=JWT_LIFETIME_SECONDS,
                scopes=SCOPES,
            )
            user_info = api_client.get_user_info(token.access_token)
        except (ApiException, ArgumentException, HTTPError, OSError, ValueError) as e:
            raise DocuSignError("Failed to obtain DocuSign JWT user token") from e

        base_uri = next(
            (
                account.base_uri
                for account in user_info.accounts or []
                if account.account_id == config.account_id
            ),
            None,
        )
        if base_uri is None:
            raise DocuSignError(
                f"Authenticated user has no access to account_id {config.account_id}"
            )
        rest_base = f"{base_uri}/restapi"
        api_client.set_base_path(rest_base)
        api_client.host = rest_base
        return api_client
