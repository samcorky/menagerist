import base64
import hashlib

import pytest

from app.modules.identity.adapters.security.in_memory_password_hasher import (
    InMemoryPasswordHasher,
)
from app.modules.identity.adapters.security.password_hasher_registry import (
    PasswordHasherRegistry,
)
from app.modules.identity.adapters.security.scrypt_password_hasher import (
    ScryptPasswordHasher,
)
from app.modules.identity.adapters.security.session_token_generator import (
    InMemorySessionTokenGenerator,
    SecretsSessionTokenGenerator,
)

FAST = ScryptPasswordHasher(n=2**4, r=8, p=1)


def test_scrypt_round_trip_and_format() -> None:
    """A hash verifies, embeds its parameters and uses a fresh salt."""
    hashed = FAST.hash("correct horse")
    scheme, n, r, p, salt, key = hashed.split("$")
    assert (scheme, n, r, p) == ("scrypt", "16", "8", "1")
    assert len(base64.b64decode(salt)) == 16
    assert len(base64.b64decode(key)) == 32
    assert FAST.verify("correct horse", hashed) is True
    assert FAST.hash("correct horse") != hashed


def test_scrypt_rejects_wrong_password() -> None:
    """A different password does not verify."""
    assert FAST.verify("nope", FAST.hash("correct horse")) is False


@pytest.mark.parametrize(
    "tampered",
    [
        "",
        "scrypt$16$8$1$bad",
        "scrypt$x$8$1$AAAA$AAAA",
        "scrypt$16$8$1$!!!$!!!",
        "scrypt$17$8$1$AAAAAAAAAAAAAAAAAAAAAA==$AAAA",
        "scrypt$4294967296$8$1$AAAAAAAAAAAAAAAAAAAAAA==$AAAA",
        "other$16$8$1$AAAA$AAAA",
    ],
)
def test_scrypt_malformed_hash_never_verifies(tampered: str) -> None:
    """Malformed or out-of-bounds hashes verify false rather than raising."""
    assert FAST.verify("correct horse", tampered) is False


def test_scrypt_tampered_key_fails() -> None:
    """Flipping a key bit makes verification fail."""
    hashed = FAST.hash("correct horse")
    head, key = hashed.rsplit("$", 1)
    forged = bytearray(base64.b64decode(key))
    forged[0] ^= 1
    forged_key = base64.b64encode(forged).decode()
    assert FAST.verify("correct horse", f"{head}${forged_key}") is False


def test_scrypt_needs_rehash_when_parameters_differ() -> None:
    """Hashes made with other parameters, or malformed ones, need rehashing."""
    old = ScryptPasswordHasher(n=2**3, r=8, p=1).hash("correct horse")
    assert FAST.needs_rehash(FAST.hash("x")) is False
    assert FAST.needs_rehash(old) is True
    assert FAST.needs_rehash("garbage") is True
    assert FAST.verify("correct horse", old) is True


def test_scrypt_default_parameters_work_within_memory_limit() -> None:
    """The production parameters (N=2^15) hash and verify."""
    hasher = ScryptPasswordHasher()
    hashed = hasher.hash("correct horse")
    assert hashed.startswith("scrypt$32768$8$1$")
    assert hasher.verify("correct horse", hashed) is True
    assert hasher.needs_rehash(hashed) is False


def test_in_memory_hasher() -> None:
    """The fake hasher round-trips and never needs rehashing."""
    hasher = InMemoryPasswordHasher()
    hashed = hasher.hash("secret")
    assert hashed.startswith("fake$")
    assert hasher.verify("secret", hashed) is True
    assert hasher.verify("other", hashed) is False
    assert hasher.needs_rehash(hashed) is False


def test_registry_hashes_with_default_and_verifies_by_prefix() -> None:
    """New hashes use the default; any registered scheme still verifies."""
    registry = PasswordHasherRegistry(
        {"scrypt": FAST, "fake": InMemoryPasswordHasher()}, default="scrypt"
    )
    fresh = registry.hash("pw")
    assert fresh.startswith("scrypt$")
    legacy = InMemoryPasswordHasher().hash("pw")
    assert registry.verify("pw", fresh) is True
    assert registry.verify("pw", legacy) is True
    assert registry.verify("wrong", legacy) is False


def test_registry_unknown_scheme_never_verifies_and_needs_rehash() -> None:
    """Unknown prefixes fail closed and are flagged for rewrite."""
    registry = PasswordHasherRegistry({"scrypt": FAST}, default="scrypt")
    assert registry.verify("pw", "mystery$abc") is False
    assert registry.verify("pw", "no-prefix") is False
    assert registry.needs_rehash("mystery$abc") is True


def test_registry_needs_rehash_for_other_scheme_or_old_parameters() -> None:
    """Non-default schemes and outdated parameters both trigger a rewrite."""
    registry = PasswordHasherRegistry(
        {"scrypt": FAST, "fake": InMemoryPasswordHasher()}, default="scrypt"
    )
    assert registry.needs_rehash(registry.hash("pw")) is False
    assert registry.needs_rehash(InMemoryPasswordHasher().hash("pw")) is True
    outdated = ScryptPasswordHasher(n=2**3, r=8, p=1).hash("pw")
    assert registry.needs_rehash(outdated) is True


def test_registry_default_must_be_registered() -> None:
    """A default that is not a known scheme is a configuration error."""
    with pytest.raises(ValueError, match="default"):
        PasswordHasherRegistry({"scrypt": FAST}, default="argon2")


def test_secrets_token_generator() -> None:
    """Real tokens are unique, URL-safe and hash to sha256 hex."""
    gen = SecretsSessionTokenGenerator()
    a, b = gen.new_token(), gen.new_token()
    assert a != b
    assert len(a) >= 43
    assert gen.token_hash(a) == hashlib.sha256(a.encode()).hexdigest()


def test_in_memory_token_generator_is_deterministic() -> None:
    """The fake yields a predictable sequence and the same sha256 hash."""
    gen = InMemorySessionTokenGenerator()
    assert [gen.new_token(), gen.new_token()] == ["token-1", "token-2"]
    assert gen.token_hash("token-1") == hashlib.sha256(b"token-1").hexdigest()


@pytest.mark.parametrize(
    "tampered",
    [
        "scrypt$262144$8$1$AAAAAAAAAAAAAAAAAAAAAA==$" + "A" * 44,
        "scrypt$16$17$1$AAAAAAAAAAAAAAAAAAAAAA==$" + "A" * 44,
        "scrypt$16$8$5$AAAAAAAAAAAAAAAAAAAAAA==$" + "A" * 44,
        "scrypt$16$8$1$AAAAAAAAAAAAAAAAAAAAAA==$AAAA",
        "scrypt$16$8$1$AAAAAAAAAAAAAAAAAAAAAA==$" + "A" * 100,
    ],
)
def test_scrypt_out_of_bounds_parameters_are_rejected(tampered: str) -> None:
    """Cost and key-length bounds fail closed without running scrypt."""
    assert FAST.verify("pw", tampered) is False
    assert FAST.needs_rehash(tampered) is True


@pytest.mark.parametrize("error", [ValueError, OverflowError, MemoryError])
def test_scrypt_backend_errors_mean_no_match(
    monkeypatch: pytest.MonkeyPatch, error: type[Exception]
) -> None:
    """If scrypt itself refuses the parameters, verify returns False."""
    hashed = FAST.hash("pw")

    def boom(*_: object, **__: object) -> bytes:
        raise error

    monkeypatch.setattr(hashlib, "scrypt", boom)
    assert FAST.verify("pw", hashed) is False
