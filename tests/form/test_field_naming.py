import pytest

from contract_generator.form import FieldNaming


def test_accepts_conventional_names() -> None:
    assert FieldNaming.is_valid("party.name")
    assert FieldNaming.is_valid("sig_date")
    assert FieldNaming.is_valid("agree-terms")
    FieldNaming.require_valid("party.name")


def test_rejects_invalid_names() -> None:
    assert not FieldNaming.is_valid(None)
    assert not FieldNaming.is_valid("")
    assert not FieldNaming.is_valid("1party")
    assert not FieldNaming.is_valid("party name")
    assert not FieldNaming.is_valid("party$name")
    assert not FieldNaming.is_valid("party\n")
    with pytest.raises(ValueError):
        FieldNaming.require_valid("party name")


def test_accepts_docusign_sign_here_name() -> None:
    assert FieldNaming.is_valid("DocusignSignHere1")
    FieldNaming.require_valid("DocusignSignHere1")


def test_sign_here_builds_docusign_transform_name() -> None:
    assert FieldNaming.sign_here(1) == "DocusignSignHere1"
    assert FieldNaming.sign_here(2) == "DocusignSignHere2"
    assert FieldNaming.SIGN_HERE_KEYWORD in FieldNaming.sign_here(3)
    assert FieldNaming.is_valid(FieldNaming.sign_here(1))
    with pytest.raises(ValueError):
        FieldNaming.sign_here(0)
