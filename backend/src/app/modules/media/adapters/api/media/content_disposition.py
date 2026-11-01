import re
from urllib.parse import quote

_MAX_NAME = 200
_UNSAFE = re.compile(r'[^\x20-\x7e]|["\\]')


def content_disposition(disposition_type: str, filename: str) -> str:
    """Build a `Content-Disposition` value that is valid for any filename.

    Follows RFC 6266: an ASCII `filename` fallback (non-ASCII, control characters,
    quotes and backslashes become `_`) plus, when that loses anything, an RFC 5987
    `filename*` carrying the UTF-8 name percent-encoded.
    """
    name = filename[:_MAX_NAME]
    cleaned = _UNSAFE.sub("_", name)
    header = f'{disposition_type}; filename="{cleaned.strip() or "download"}"'
    if cleaned != name:
        header += f"; filename*=UTF-8''{quote(name, safe='')}"
    return header
