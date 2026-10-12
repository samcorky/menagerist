"""The process-wide cap on concurrent password hashing."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

from app.modules.identity.adapters.security.bounded_password_hasher import (
    BoundedPasswordHasher,
)
from app.modules.identity.adapters.security.in_memory_password_hasher import (
    InMemoryPasswordHasher,
)


class _Tracking(InMemoryPasswordHasher):
    """Records the most calls ever running at once."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.running = 0
        self.peak = 0

    def _enter(self) -> None:
        with self._lock:
            self.running += 1
            self.peak = max(self.peak, self.running)
        time.sleep(0.02)
        with self._lock:
            self.running -= 1

    def hash(self, password: str) -> str:
        self._enter()
        return super().hash(password)

    def verify(self, password: str, hashed: str) -> bool:
        self._enter()
        return super().verify(password, hashed)


def test_hash_and_verify_never_exceed_the_concurrency() -> None:
    """Twenty parallel calls through a cap of two never run more than two at once."""
    inner = _Tracking()
    hasher = BoundedPasswordHasher(inner, concurrency=2)

    def work(i: int) -> bool:
        stored = hasher.hash(f"password-{i}")
        return hasher.verify(f"password-{i}", stored)

    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(work, range(20)))

    assert all(results)
    assert inner.peak == 2


def test_the_cap_is_at_least_one_and_rehash_checks_are_not_limited() -> None:
    """A zero cap still works, and needs_rehash passes straight through."""
    hasher = BoundedPasswordHasher(InMemoryPasswordHasher(), concurrency=0)
    stored = hasher.hash("password-123")
    assert hasher.verify("password-123", stored)
    assert not hasher.verify("nope", stored)
    assert hasher.needs_rehash(stored) is False


def test_the_composition_root_wires_one_bounded_hasher_per_process() -> None:
    """The shared hasher is bounded and the decoy hash verifies against it."""
    from app.modules.identity.adapters.api import dependencies

    dependencies._hasher.cache_clear()
    dependencies._decoy_hash.cache_clear()
    try:
        hasher = dependencies.get_password_hasher()
        assert isinstance(hasher, BoundedPasswordHasher)
        assert dependencies.get_password_hasher() is hasher
        assert not hasher.verify("not-the-decoy", dependencies.get_decoy_hash())
    finally:
        dependencies._hasher.cache_clear()
        dependencies._decoy_hash.cache_clear()
