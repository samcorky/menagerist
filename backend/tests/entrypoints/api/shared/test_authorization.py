import uuid

from app.entrypoints.api.shared.authorization import AllowAllAuthorizationAdapter
from app.shared_kernel.actor import Actor


async def test_allow_all_authorization_adapter_never_raises() -> None:
    """The v1 stub permits any actor to perform any action."""
    adapter = AllowAllAuthorizationAdapter()
    actor = Actor(id=uuid.uuid4(), roles=frozenset())

    await adapter.check(actor, "graph.node.create")
