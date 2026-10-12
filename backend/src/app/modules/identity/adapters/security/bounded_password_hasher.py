import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.modules.identity.ports.password_hasher import PasswordHasher


class BoundedPasswordHasher:
    """Caps how many hash and verify calls run at once, process-wide.

    Each scrypt call allocates about 32 MiB, so an unbounded flood of sign-ins
    could exhaust memory. Callers beyond the cap wait for a slot. One instance
    is shared by the whole process (the composition root caches it).
    """

    def __init__(self, inner: PasswordHasher, *, concurrency: int) -> None:
        """Wrap `inner`, allowing `concurrency` (at least 1) calls at a time."""
        self._inner = inner
        self._slots = threading.BoundedSemaphore(max(1, concurrency))

    def hash(self, password: str) -> str:
        """Return a self-describing hash of `password`, waiting for a slot."""
        with self._slots:
            return self._inner.hash(password)

    def verify(self, password: str, hashed: str) -> bool:
        """Whether `password` matches `hashed`, waiting for a slot."""
        with self._slots:
            return self._inner.verify(password, hashed)

    def needs_rehash(self, hashed: str) -> bool:
        """Whether `hashed` should be rewritten (cheap, so not limited)."""
        return self._inner.needs_rehash(hashed)
