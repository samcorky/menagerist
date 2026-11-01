"""Keep passwords out of logs, reprs and error messages."""

from sqlalchemy.engine import make_url

_SECRET_QUERY_KEYS = {"password", "sslpassword"}
_MASK = "***"


def mask_dsn(url: object) -> str:
    """Return the DSN with its password (userinfo and query) replaced by `***`."""
    try:
        parsed = make_url(str(url))
    except Exception:
        return "<unparseable database url>"
    query = {
        key: _MASK if key in _SECRET_QUERY_KEYS else value
        for key, value in parsed.query.items()
    }
    return parsed.set(query=query).render_as_string(hide_password=True)
