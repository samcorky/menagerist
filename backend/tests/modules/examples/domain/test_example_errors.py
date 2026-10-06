"""Tests for the examples domain errors."""

from app.modules.examples.domain.errors import InstallFailedError, SlugClashError
from app.shared_kernel.errors import DomainError


def test_slug_clash_error_names_the_kind_and_slug() -> None:
    """The message and attributes carry the clashing kind and slug."""
    error = SlugClashError(kind="an item type", slug="record")
    expected = "You already have an item type called 'record'."
    assert str(error) == f"{expected} Rename or remove it, then try again."
    assert error.kind == "an item type"
    assert error.slug == "record"


def test_install_failed_error_is_not_a_domain_error() -> None:
    """It reports as a server failure, not a client error."""
    assert not issubclass(InstallFailedError, DomainError)
