from typing import Any

from fastapi.dependencies import utils

from app.entrypoints.api.shared import signature_cache


def _dependency(value: int = 1) -> int:
    return value


class _Unhashable:
    __hash__ = None  # type: ignore[assignment]

    def __call__(self, value: int = 1) -> int:
        return value


def test_repeated_analysis_of_one_callable_returns_the_same_signature() -> None:
    """A shared dependency is analysed once, however many routes use it."""
    signature_cache.install()

    first = utils.get_typed_signature(_dependency)

    assert utils.get_typed_signature(_dependency) is first


def test_install_is_idempotent() -> None:
    """Installing twice does not wrap the cache in a second cache."""
    signature_cache.install()
    installed = utils.get_typed_signature

    signature_cache.install()

    assert utils.get_typed_signature is installed


def test_unhashable_callable_is_analysed_without_caching() -> None:
    """A callable that cannot be a cache key still gets its signature."""
    signature_cache.install()
    dependency: Any = _Unhashable()

    signature = utils.get_typed_signature(dependency)

    assert list(signature.parameters) == ["value"]
    assert utils.get_typed_signature(dependency) is not signature
