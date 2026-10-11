from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from app.modules.identity.ports.password_hasher import PasswordHasher


def _scheme_of(hashed: str) -> str:
    return hashed.partition("$")[0]


class PasswordHasherRegistry:
    """`PasswordHasher` over several schemes, chosen by each hash's prefix.

    New hashes use the default scheme; any registered scheme still verifies.
    """

    def __init__(self, schemes: Mapping[str, PasswordHasher], default: str) -> None:
        if default not in schemes:
            raise ValueError(f"The default hasher '{default}' is not registered.")
        self._schemes = dict(schemes)
        self._default = default

    def hash(self, password: str) -> str:
        """Hash `password` with the default scheme."""
        return self._schemes[self._default].hash(password)

    def verify(self, password: str, hashed: str) -> bool:
        """Verify with the scheme named by the prefix; unknown schemes never match."""
        hasher = self._schemes.get(_scheme_of(hashed))
        return hasher is not None and hasher.verify(password, hashed)

    def needs_rehash(self, hashed: str) -> bool:
        """Whether `hashed` is another scheme, unknown, or has outdated parameters."""
        scheme = _scheme_of(hashed)
        return scheme != self._default or self._schemes[scheme].needs_rehash(hashed)
