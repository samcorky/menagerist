from datetime import UTC, datetime, timedelta

from app.modules.identity.domain.throttle import (
    AttemptWindow,
    ThrottlePolicy,
    after_failure,
)

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
WINDOW = timedelta(minutes=15)


def test_policy_defaults() -> None:
    """Five per username, twenty per address, in fifteen minutes."""
    policy = ThrottlePolicy()
    assert (policy.username_limit, policy.ip_limit, policy.window) == (5, 20, WINDOW)


def test_first_failure_starts_a_window() -> None:
    """With no counter, one failure opens a window and does not lock."""
    assert after_failure(None, now=NOW, limit=5, window=WINDOW) == AttemptWindow(
        count=1, window_start=NOW
    )


def test_the_failure_reaching_the_limit_locks_until_the_window_ends() -> None:
    """Failures count in a fixed window; the fifth locks until it closes."""
    state: AttemptWindow | None = None
    for minute in range(4):
        state = after_failure(
            state, now=NOW + timedelta(minutes=minute), limit=5, window=WINDOW
        )
        assert state.locked_until is None
    state = after_failure(state, now=NOW + timedelta(minutes=4), limit=5, window=WINDOW)
    assert (state.count, state.locked_until) == (5, NOW + WINDOW)


def test_a_failure_after_the_window_restarts_the_count() -> None:
    """The window is fixed: a late failure begins a new one."""
    locked = AttemptWindow(count=5, window_start=NOW, locked_until=NOW + WINDOW)
    state = after_failure(locked, now=NOW + WINDOW, limit=5, window=WINDOW)
    assert state == AttemptWindow(count=1, window_start=NOW + WINDOW)


def test_a_limit_of_one_locks_at_once() -> None:
    """Limits are read from the call, so one failure can lock."""
    state = after_failure(None, now=NOW, limit=1, window=WINDOW)
    assert state.locked_until == NOW + WINDOW
