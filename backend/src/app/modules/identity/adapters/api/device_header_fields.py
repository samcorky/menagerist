from typing import TYPE_CHECKING

from app.shared_kernel.log_safe import loggable

if TYPE_CHECKING:
    from collections.abc import Mapping

_HEADER_FIELDS = {
    "user_agent": "User-Agent",
    "sec_ch_ua": "Sec-CH-UA",
    "sec_ch_ua_mobile": "Sec-CH-UA-Mobile",
    "sec_ch_ua_platform": "Sec-CH-UA-Platform",
    "x_forwarded_for": "X-Forwarded-For",
    "x_forwarded_proto": "X-Forwarded-Proto",
    "forwarded": "Forwarded",
}


def _safe_value(value: str) -> str:
    """Escape controls and cap a logged value at 256 characters."""
    safe = loggable(value, limit=256)
    return safe if len(safe) <= 256 else f"{safe[:253]}..."


def device_header_fields(
    headers: Mapping[str, str], client_ip: str | None
) -> dict[str, str | None]:
    """Return the allowlisted, bounded sign-in headers and resolved client address."""
    fields = {
        field: (
            _safe_value(value) if (value := headers.get(header)) is not None else None
        )
        for field, header in _HEADER_FIELDS.items()
    }
    fields["client_ip"] = _safe_value(client_ip) if client_ip is not None else None
    return fields
