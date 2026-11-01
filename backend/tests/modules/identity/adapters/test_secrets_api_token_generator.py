import hashlib
import re

import pytest

from app.modules.identity.adapters.security.secrets_api_token_generator import (
    SecretsApiTokenGenerator,
)

generator = SecretsApiTokenGenerator()


def test_new_token_format() -> None:
    """A token is `mnst_<id hex>_<64 hex secret>`."""
    token = generator.new_token()
    assert re.fullmatch(r"[0-9a-f]{64}", token.secret)
    assert token.plaintext == f"mnst_{token.token_id.hex}_{token.secret}"


def test_new_tokens_differ() -> None:
    """Two tokens never share an id or secret."""
    first, second = generator.new_token(), generator.new_token()
    assert first.token_id != second.token_id
    assert first.secret != second.secret


def test_parse_round_trips() -> None:
    """Parsing a generated token returns its id and secret."""
    token = generator.new_token()
    parsed = generator.parse(token.plaintext)
    assert parsed is not None
    assert parsed.token_id == token.token_id
    assert parsed.secret == token.secret


_ID = "01a1682a133370b3acf0f1d86f0e1f14"
_SECRET = "ab" * 32


@pytest.mark.parametrize(
    "value",
    [
        "",
        f"other_{_ID}_{_SECRET}",
        f"mnst_{'z' * 32}_{_SECRET}",
        f"mnst_{_ID[:-1]}_{_SECRET}",
        f"mnst_{_ID}_{_SECRET[:-1]}",
        f"mnst_{_ID}_{'z' * 64}",
        f"mnst_{_ID}_{_SECRET}_extra",
        f"mnst_{_ID}_{_SECRET}\n",
        f" mnst_{_ID}_{_SECRET}",
    ],
)
def test_parse_rejects_malformed(value: str) -> None:
    """Anything but the exact format parses to None."""
    assert generator.parse(value) is None


def test_hash_is_sha256_hex() -> None:
    """The stored value is the SHA-256 hex digest of the secret."""
    assert generator.hash("abc") == hashlib.sha256(b"abc").hexdigest()


def test_matches_only_right_pair() -> None:
    """Only the right secret matches its stored hash."""
    stored = generator.hash("right")
    assert generator.matches("right", stored)
    assert not generator.matches("wrong", stored)
