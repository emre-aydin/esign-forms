from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
from collections.abc import Iterable


class ConnectHmacVerifier:
    """Verifies DocuSign Connect HMAC-SHA256 signatures (``X-DocuSign-Signature-N`` headers).

    Always verify against the **raw** request body bytes, before parsing — never re-serialize.
    Comparison is constant-time.
    """

    def verify(
        self, payload: bytes | None, base64_signature: str | None, secret: str | None
    ) -> bool:
        if payload is None or base64_signature is None or secret is None:
            return False
        expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).digest()
        try:
            provided = base64.b64decode(base64_signature.strip(), validate=True)
        except (binascii.Error, ValueError):
            return False
        return hmac.compare_digest(expected, provided)

    def verify_any(
        self,
        payload: bytes | None,
        base64_signatures: Iterable[str | None] | None,
        secret: str | None,
    ) -> bool:
        """True if any of the signatures matches (Connect sends one header per active key)."""
        if base64_signatures is None:
            return False
        return any(
            signature is not None and self.verify(payload, signature, secret)
            for signature in base64_signatures
        )
