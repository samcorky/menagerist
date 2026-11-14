import uuid

from app.modules.examples.adapters.persistence.unit_of_work import (
    create_in_memory_example_uow,
)
from app.modules.examples.application.claim_orphaned_installations import (
    ClaimOrphanedInstallations,
    ClaimOrphanedInstallationsCommand,
)
from app.modules.examples.ports.unit_of_work import ExampleRepos
from app.modules.transfer.adapters.persistence.in_memory_run_repository import (
    InMemoryRunRepository,
)
from app.modules.transfer.domain.run import Run
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import SYSTEM_ACTOR


async def test_claims_system_owned_installations_and_commits() -> None:
    """System-owned installations move to the new owner; another user's stay."""
    installations = InMemoryRunRepository()
    uow = create_in_memory_example_uow(ExampleRepos(runs=installations))
    system = Run.start("one", SYSTEM_ACTOR.id)
    theirs = Run.start("two", uuid.uuid7())
    await installations.add(system)
    await installations.add(theirs)
    owner = uuid.uuid7()

    count = await ClaimOrphanedInstallations(uow, InMemoryAccessGuard()).handle(
        ClaimOrphanedInstallationsCommand(owner_id=owner), SYSTEM_ACTOR
    )

    assert count == 1
    assert system.owner_id == owner
    assert theirs.owner_id != owner
    assert getattr(uow, "committed", False)
