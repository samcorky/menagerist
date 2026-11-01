from dataclasses import dataclass
from enum import StrEnum

from app.modules.examples.domain.errors import InvalidInstallationStateError
from app.modules.examples.domain.installation import (
    EntityKind,
    EntityRecord,
    Installation,
    Outcome,
)

KEEP_EDITED = "edited"
KEEP_USER_DATA = "has your connections, files or collections"
KEEP_IN_USE = "still in use"
KEEP_SHARED = "still used by other people's examples"


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


SHARED_TYPE_KINDS = frozenset({EntityKind.ITEM_TYPE, EntityKind.RELATIONSHIP_TYPE})


def holds_shared_type(installation: Installation, record: EntityRecord) -> bool:
    """Whether `installation` still stands behind the type `record` describes.

    True for a type an active installation owns, and for one a removed installation
    left for other people's content (kept as shared or in use). Item and
    relationship types are shared structure, so other people's installs of the
    same pack may reuse these.
    """
    if record.kind not in SHARED_TYPE_KINDS:
        return False
    if record.outcome is Outcome.OWNED:
        return installation.is_active
    return record.outcome is Outcome.KEPT and record.reason in (
        KEEP_SHARED,
        KEEP_IN_USE,
    )


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
