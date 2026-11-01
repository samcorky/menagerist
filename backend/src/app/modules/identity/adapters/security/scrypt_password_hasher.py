import base64
import hashlib
import hmac
import os

SCHEME = "scrypt"
_SALT_BYTES = 16
_KEY_BYTES = 32
# Upper bounds so a tampered hash cannot make verification allocate huge memory.
_MAX_N = 2**17
_MAX_R = 16
_MAX_P = 4
_MIN_KEY_BYTES = 16
_MAX_KEY_BYTES = 64


def _maxmem(n: int, r: int, p: int) -> int:
    """Memory limit for `hashlib.scrypt`: twice the roughly 128*r*(n+p+2) it needs."""
    return 2 * 128 * r * (n + p + 2)


class ScryptPasswordHasher:
    """`PasswordHasher` using stdlib scrypt.

    Format: `scrypt$N$r$p$salt_b64$key_b64`, so the cost can be raised later
    while older hashes keep verifying.
    """

    def __init__(self, *, n: int = 2**15, r: int = 8, p: int = 1) -> None:
        self._n, self._r, self._p = n, r, p

    def hash(self, password: str) -> str:
        """Return a scrypt hash of `password` with a fresh random salt."""
        salt = os.urandom(_SALT_BYTES)
        key = self._derive(password, salt, self._n, self._r, self._p, _KEY_BYTES)
        return "$".join(
            (
                SCHEME,
                str(self._n),
                str(self._r),
                str(self._p),
                base64.b64encode(salt).decode(),
                base64.b64encode(key).decode(),
            )
        )

    def verify(self, password: str, hashed: str) -> bool:
        """Whether `password` matches `hashed`; malformed hashes never match."""
        parsed = _parse(hashed)
        if parsed is None:
            return False
        n, r, p, salt, key = parsed
        try:
            candidate = self._derive(password, salt, n, r, p, len(key))
        except ValueError, OverflowError, MemoryError:
            return False
        return hmac.compare_digest(candidate, key)

    def needs_rehash(self, hashed: str) -> bool:
        """Whether `hashed` is malformed or uses other parameters than this hasher."""
        parsed = _parse(hashed)
        if parsed is None:
            return True
        n, r, p, _, _ = parsed
        return (n, r, p) != (self._n, self._r, self._p)

    @staticmethod
    def _derive(
        password: str, salt: bytes, n: int, r: int, p: int, length: int
    ) -> bytes:
        return hashlib.scrypt(
            password.encode(),
            salt=salt,
            n=n,
            r=r,
            p=p,
            maxmem=_maxmem(n, r, p),
            dklen=length,
        )


def _parse(hashed: str) -> tuple[int, int, int, bytes, bytes] | None:
    """Split a stored hash into its parts, or `None` if it is malformed."""
    parts = hashed.split("$")
    if len(parts) != 6 or parts[0] != SCHEME:
        return None
    try:
        n, r, p = int(parts[1]), int(parts[2]), int(parts[3])
        salt = base64.b64decode(parts[4], validate=True)
        key = base64.b64decode(parts[5], validate=True)
    except ValueError:
        return None
    if not (2 <= n <= _MAX_N and n & (n - 1) == 0):
        return None
    if not (
        1 <= r <= _MAX_R
        and 1 <= p <= _MAX_P
        and salt
        and _MIN_KEY_BYTES <= len(key) <= _MAX_KEY_BYTES
    ):
        return None
    return n, r, p, salt, key
