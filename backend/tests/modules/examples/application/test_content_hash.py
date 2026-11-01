from app.modules.examples.application.content_hash import content_hash


def test_key_order_does_not_matter_at_any_depth() -> None:
    """Reordering keys at any depth leaves the hash unchanged."""
    a = {"x": 1, "y": {"b": [1, 2], "a": None}}
    b = {"y": {"a": None, "b": [1, 2]}, "x": 1}
    assert content_hash(a) == content_hash(b)


def test_a_changed_value_changes_the_hash() -> None:
    """Changing a value or list order changes the hash."""
    assert content_hash({"x": 1}) != content_hash({"x": 2})
    assert content_hash({"x": [1, 2]}) != content_hash({"x": [2, 1]})


def test_unicode_is_hashed_as_written() -> None:
    """Non-ASCII text hashes deterministically."""
    assert content_hash({"x": "café 🎵"}) == content_hash({"x": "café 🎵"})


def test_the_hash_is_stable() -> None:
    """The hash of a known payload is pinned."""
    # SHA-256 of canonical JSON `{"x":1}`; a change alters every stored hash
    assert content_hash({"x": 1}) == (
        "5041bf1f713df204784353e82f6a4a535931cb64f1f4b4a5aeaffcb720918b22"
    )


def test_a_non_ascii_hash_is_pinned() -> None:
    """Non-ASCII text hashes as raw UTF-8, not as JSON escapes."""
    # SHA-256 of the UTF-8 bytes of `{"x":"café 🎵"}`
    assert content_hash({"x": "café 🎵"}) == (
        "3d74485af66a2a1ccb81748610e6e948dee41585de84bb66873322a28c3563c8"
    )
