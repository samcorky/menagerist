from dataclasses import dataclass
from datetime import datetime

from app.modules.identity.domain.user import User


@dataclass(kw_only=True, frozen=True)
class UserListing:
    """An account and, if its username is locked out of signing in, until when."""

    user: User
    locked_until: datetime | None = None
