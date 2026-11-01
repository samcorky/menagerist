from dataclasses import dataclass, field


@dataclass(kw_only=True, frozen=True)
class ClientDevice:
    """Device details captured from request headers at session creation."""

    user_agent: str | None = field(default=None, repr=False)
    platform: str | None = None
    mobile: bool | None = None
