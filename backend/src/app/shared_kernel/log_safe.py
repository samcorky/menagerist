import re

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def loggable(text: str, *, limit: int = 100) -> str:
    """Return client-supplied `text` safe to log: controls escaped, length capped.

    A raw escape sequence could rewrite an operator's terminal, so each control
    character becomes a visible hex escape. Text longer than `limit` is cut and marked.
    """
    escaped = _CONTROL_CHARS.sub(lambda m: "\\x" + format(ord(m.group()), "02x"), text)
    return escaped if len(escaped) <= limit else f"{escaped[:limit]}..."
