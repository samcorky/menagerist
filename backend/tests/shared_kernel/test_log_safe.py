from app.shared_kernel.log_safe import escape_controls, loggable


def test_plain_text_is_unchanged() -> None:
    """Ordinary text, including non-ASCII letters, passes through."""
    assert loggable("café.jpg") == "café.jpg"


def test_control_characters_are_escaped() -> None:
    """Escape, newline, DEL and C1 controls become visible escapes."""
    assert loggable("a\x1b[0m\nb\x7f\x9b") == (
        "a" + "\\x1b" + "[0m" + "\\x0a" + "b" + "\\x7f" + "\\x9b"
    )


def test_long_text_is_cut_and_marked() -> None:
    """Text over the limit is truncated with an ellipsis."""
    assert loggable("x" * 10, limit=4) == "xxxx..."
    assert loggable("x" * 4, limit=4) == "xxxx"


def test_layout_can_be_kept_while_other_controls_are_escaped() -> None:
    """Newlines and tabs survive for multi-line text; escape sequences do not."""
    assert escape_controls("a\n\tb\x1b", keep_layout=True) == "a\n\tb\\x1b"
    assert escape_controls("a\n\tb\x1b") == "a\\x0a\\x09b\\x1b"
