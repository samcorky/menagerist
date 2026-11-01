import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
import time_machine
from structlog.testing import capture_logs

from app.modules.identity.application.revoke_own_api_token import (
    RevokeOwnApiTokenCommand,
)
from app.modules.identity.domain.errors import ApiTokenNotFoundError

if TYPE_CHECKING:
    from tests.modules.identity.application.conftest import ActorFor, Cases, IssueToken
    from tests.modules.identity.conftest import MakeUser, World

NOW = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)


@time_machine.travel(NOW, tick=False)
async def test_revoke_deletes_the_row_and_logs_the_id(
    cases: Cases,
    world: World,
    make_user: MakeUser,
    actor_for: ActorFor,
    issue_token: IssueToken,
) -> None:
    """The token is gone and the value no longer authenticates."""
    user = make_user()
    await world.users.add(user)
    created = await issue_token(user)

    with capture_logs() as logs:
        await cases.revoke_own_api_token.handle(
            RevokeOwnApiTokenCommand(token_id=created.token.id), actor_for(user)
        )

    assert await world.tokens.get(created.token.id) is None
    event = next(e for e in logs if e["event"] == "api token revoked")
    assert event["token_id"] == created.token.id


@time_machine.travel(NOW, tick=False)
async def test_unknown_and_foreign_ids_are_not_found(
    cases: Cases,
    world: World,
    make_user: MakeUser,
    actor_for: ActorFor,
    issue_token: IssueToken,
) -> None:
    """Another user's token is indistinguishable from none, and survives."""
    alice, bob = make_user("alice"), make_user("bob")
    await world.users.add(alice)
    await world.users.add(bob)
    theirs = await issue_token(bob)

    for token_id in (uuid.uuid7(), theirs.token.id):
        with pytest.raises(ApiTokenNotFoundError):
            await cases.revoke_own_api_token.handle(
                RevokeOwnApiTokenCommand(token_id=token_id), actor_for(alice)
            )
    assert await world.tokens.get(theirs.token.id) is not None
