import re

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f-\x9f]")
# Multi-line text (a traceback) keeps its line breaks and tabs readable.
_CONTROL_CHARS_EXCEPT_LAYOUT = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def escape_controls(text: str, *, keep_layout: bool = False) -> str:
    r"""Return `text` with each control character replaced by a visible `\xNN` escape.

    A raw escape sequence could rewrite an operator's terminal. With `keep_layout`,
    newlines and tabs stay as they are, for text that is multi-line by design.
    """
    pattern = _CONTROL_CHARS_EXCEPT_LAYOUT if keep_layout else _CONTROL_CHARS
    return pattern.sub(lambda m: "\\x" + format(ord(m.group()), "02x"), text)


def loggable(text: str, *, limit: int = 100) -> str:
    """Return client-supplied `text` safe to log: controls escaped, length capped.

    Text longer than `limit` is cut and marked.
    """
    escaped = escape_controls(text)
    return escaped if len(escaped) <= limit else f"{escaped[:limit]}..."
