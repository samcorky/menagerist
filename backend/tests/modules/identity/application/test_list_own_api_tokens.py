from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import time_machine

from app.modules.identity.application.list_own_api_tokens import ListOwnApiTokensQuery

if TYPE_CHECKING:
    from tests.modules.identity.application.conftest import ActorFor, Cases, IssueToken
    from tests.modules.identity.conftest import MakeUser, World

NOW = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)


@time_machine.travel(NOW, tick=False)
async def test_lists_own_unexpired_tokens_newest_first(
    cases: Cases,
    world: World,
    make_user: MakeUser,
    actor_for: ActorFor,
    issue_token: IssueToken,
) -> None:
    """Expired and foreign tokens are left out."""
    alice, bob = make_user("alice"), make_user("bob")
    await world.users.add(alice)
    await world.users.add(bob)
    short = await issue_token(alice, name="short", days=1)
    with time_machine.travel(NOW + timedelta(hours=1), tick=False):
        newer = await issue_token(alice, name="newer", days=30)
    await issue_token(bob, name="bobs")

    with time_machine.travel(NOW + timedelta(hours=2), tick=False):
        listed = await cases.list_own_api_tokens.handle(
            ListOwnApiTokensQuery(), actor_for(alice)
        )
    assert [t.id for t in listed] == [newer.token.id, short.token.id]

    with time_machine.travel(NOW + timedelta(days=2), tick=False):
        later = await cases.list_own_api_tokens.handle(
            ListOwnApiTokensQuery(), actor_for(alice)
        )
    assert [t.id for t in later] == [newer.token.id]
