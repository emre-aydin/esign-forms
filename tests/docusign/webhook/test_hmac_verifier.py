from esign_forms.docusign.webhook import ConnectHmacVerifier

# Precomputed with: Base64(HMAC-SHA256(key="topsecret", body='{"hello":"world"}'))
BODY = b'{"hello":"world"}'
SECRET = "topsecret"
VALID_SIGNATURE = "r9AGF8649j5l6lwxDwa/eMOQHnpxPbUy4l2iatY8cjY="

verifier = ConnectHmacVerifier()


def test_accepts_valid_signature() -> None:
    assert verifier.verify(BODY, VALID_SIGNATURE, SECRET)
    assert verifier.verify(BODY, f"  {VALID_SIGNATURE}\n", SECRET)


def test_rejects_wrong_secret() -> None:
    assert not verifier.verify(BODY, VALID_SIGNATURE, "not-the-secret")


def test_rejects_tampered_body() -> None:
    assert not verifier.verify(b'{"hello":"WORLD"}', VALID_SIGNATURE, SECRET)


def test_rejects_malformed_base64() -> None:
    assert not verifier.verify(BODY, "not base64 !!!", SECRET)


def test_rejects_nulls() -> None:
    assert not verifier.verify(None, VALID_SIGNATURE, SECRET)
    assert not verifier.verify(BODY, None, SECRET)
    assert not verifier.verify(BODY, VALID_SIGNATURE, None)


def test_verify_any_matches_one_of_several() -> None:
    assert verifier.verify_any(BODY, ["AAAA", None, VALID_SIGNATURE, "BBBB"], SECRET)


def test_verify_any_fails_when_none_match() -> None:
    assert not verifier.verify_any(BODY, ["AAAA", "BBBB"], SECRET)
    assert not verifier.verify_any(BODY, None, SECRET)
