import inspect

from app.shared_kernel.authorisation import AuthorisationPort


def test_authorisation_port_declares_check_method() -> None:
    """AuthorisationPort Protocol exposes an async `check` coroutine."""
    assert inspect.iscoroutinefunction(AuthorisationPort.check)
