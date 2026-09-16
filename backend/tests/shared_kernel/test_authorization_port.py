import inspect

from app.shared_kernel.authorization import AuthorizationPort


def test_authorization_port_declares_check_method() -> None:
    """AuthorizationPort Protocol exposes an async `check` coroutine."""
    assert inspect.iscoroutinefunction(AuthorizationPort.check)
