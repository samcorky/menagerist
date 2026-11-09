from dataclasses import dataclass
from enum import StrEnum

from app.modules.examples.domain.errors import InvalidInstallationStateError
from app.modules.examples.domain.installation import EntityRecord, Outcome

KEEP_EDITED = "edited"
KEEP_USER_DATA = "has your connections, files or collections"
KEEP_IN_USE = "still in use"


class Action(StrEnum):
    """What to do with one owned entity on removal."""

    REMOVE = "remove"
    KEEP = "keep"
    ALREADY_GONE = "already_gone"


@dataclass(kw_only=True, frozen=True, eq=False)
class RemovalDecision:
    """The verdict for one entity, with the reason when it is kept."""

    action: Action
    reason: str | None = None


def decide_removal(
    record: EntityRecord,
    current_hash: str | None,
    *,
    has_user_data: bool,
    still_in_use: bool,
) -> RemovalDecision:
    """Decide whether an owned entity may be removed.

    `current_hash` is the hash of the entity's content now, or `None` if it is
    gone. Precedence when several reasons apply: edited, then user data, then in
    use.
    """
    if record.outcome is not Outcome.OWNED:
        raise InvalidInstallationStateError("only owned entities are decided")
    if current_hash is None:
        return RemovalDecision(action=Action.ALREADY_GONE)
    if current_hash != record.content_hash:
        return RemovalDecision(action=Action.KEEP, reason=KEEP_EDITED)
    if has_user_data:
        return RemovalDecision(action=Action.KEEP, reason=KEEP_USER_DATA)
    if still_in_use:
        return RemovalDecision(action=Action.KEEP, reason=KEEP_IN_USE)
    return RemovalDecision(action=Action.REMOVE)
