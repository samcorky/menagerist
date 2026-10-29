import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.entrypoints.api.shared.access_guard import RoleAccessGuard
from app.entrypoints.api.shared.access_policy import OwnerAccessPolicy
from app.entrypoints.api.shared.authorisation import RoleAuthorisationAdapter
from app.modules.system.adapters.persistence.in_memory_update_check_store import (
    InMemoryUpdateCheckStore,
)
from app.modules.system.adapters.persistence.unit_of_work import (
    create_in_memory_system_uow,
)
from app.modules.system.adapters.platform.in_memory_app_info_adapter import (
    InMemoryAppInfoAdapter,
)
from app.modules.system.adapters.platform.in_memory_release_provider import (
    InMemoryReleaseProvider,
)
from app.modules.system.application.check_for_updates import (
    CheckForUpdates,
    CheckForUpdatesCommand,
)
from app.modules.system.application.get_version_detail import (
    GetVersionDetail,
    GetVersionDetailQuery,
    VersionDetailSources,
)
from app.modules.system.domain.app_info import AppInfo
from app.modules.system.domain.release import (
    CheckFailure,
    Release,
    ReleaseChannel,
    UpdateStatus,
)
from app.shared_kernel.actor import SYSTEM_ACTOR, Actor
from app.shared_kernel.errors import ForbiddenError

GUARD = RoleAccessGuard(RoleAuthorisationAdapter(), OwnerAccessPolicy())
ADMIN = Actor(id=uuid.UUID(int=1), roles=frozenset({"admin"}))
MEMBER = Actor(id=uuid.UUID(int=2), roles=frozenset({"member"}))
NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
REPOSITORY = "https://github.com/o/r"


def app_info(*, repository_url: str | None = REPOSITORY) -> AppInfo:
    """App info."""
    return AppInfo(
        name="menagerist",
        version="0.2026.10.0",
        dirty=False,
        repository_url=repository_url,
        migration_head=("abc",),
    )


def release(version: str, *, prerelease: bool = False) -> Release:
    """Release."""
    return Release(
        version=version,
        url=f"https://github.com/o/r/releases/tag/{version}",
        prerelease=prerelease,
    )


class Harness:
    """Harness."""

    def __init__(
        self,
        releases: list[Release] | None = None,
        *,
        failure: CheckFailure | None = None,
        repository_url: str | None = REPOSITORY,
    ) -> None:
        self.store = InMemoryUpdateCheckStore()
        self.uow = create_in_memory_system_uow(self.store)
        self.provider = InMemoryReleaseProvider(releases, failure=failure)
        self.info = InMemoryAppInfoAdapter(app_info(repository_url=repository_url))

    def check(self) -> CheckForUpdates:
        """Check."""
        return CheckForUpdates(
            self.uow, GUARD, app_info=self.info, provider=self.provider
        )

    def detail(self) -> GetVersionDetail:
        """Detail."""
        return GetVersionDetail(
            VersionDetailSources(app_info=self.info, updates=self.store), GUARD
        )


def command(
    *, at: datetime = NOW, channel: ReleaseChannel = ReleaseChannel.STABLE
) -> CheckForUpdatesCommand:
    """Command."""
    return CheckForUpdatesCommand(channel=channel, now=at)


async def test_a_check_stores_the_newest_eligible_release() -> None:
    """A check stores the newest eligible release."""
    harness = Harness([release("0.2026.11.0"), release("0.2026.12.0rc1")])

    outcome = await harness.check().handle(command(), ADMIN)

    assert outcome is not None
    assert outcome.latest is not None
    assert outcome.latest.version == "0.2026.11.0"
    assert outcome.failure is None
    assert harness.uow.committed
    detail = await harness.detail().handle(GetVersionDetailQuery(), ADMIN)
    assert detail.release is not None
    assert detail.release.status is UpdateStatus.UPDATE_AVAILABLE
    assert detail.release.checked_at == NOW


async def test_the_system_actor_can_check_for_the_schedule() -> None:
    """The system actor can check for the schedule."""
    harness = Harness([release("0.2026.11.0")])

    assert await harness.check().handle(command(), SYSTEM_ACTOR) is not None


async def test_a_member_cannot_trigger_a_check() -> None:
    """A member cannot trigger a check."""
    harness = Harness([release("0.2026.11.0")])

    with pytest.raises(ForbiddenError):
        await harness.check().handle(command(), MEMBER)
    assert harness.provider.calls == []


async def test_reading_the_detail_never_contacts_the_source() -> None:
    """Reading the detail never contacts the source."""
    harness = Harness([release("0.2026.11.0")])

    detail = await harness.detail().handle(GetVersionDetailQuery(), ADMIN)

    assert harness.provider.calls == []
    assert detail.release is not None
    assert detail.release.status is UpdateStatus.UNKNOWN


async def test_a_failure_is_recorded_and_the_last_answer_kept() -> None:
    """A failure is recorded and the last answer kept."""
    harness = Harness([release("0.2026.11.0")])
    await harness.check().handle(command(), ADMIN)
    harness.provider.failure = CheckFailure.RATE_LIMITED

    later = NOW + timedelta(hours=1)
    outcome = await harness.check().handle(command(at=later), ADMIN)

    assert outcome is not None
    assert outcome.failure is CheckFailure.RATE_LIMITED
    assert outcome.last_attempt_at == later
    assert outcome.last_success_at == NOW
    detail = await harness.detail().handle(GetVersionDetailQuery(), ADMIN)
    assert detail.release is not None
    assert detail.release.status is UpdateStatus.UPDATE_AVAILABLE
    assert detail.release.failure is CheckFailure.RATE_LIMITED


async def test_a_first_check_that_fails_stays_unknown() -> None:
    """A first check that fails stays unknown."""
    harness = Harness(failure=CheckFailure.NETWORK)

    outcome = await harness.check().handle(command(), ADMIN)

    assert outcome is not None
    assert outcome.last_success_at is None
    detail = await harness.detail().handle(GetVersionDetailQuery(), ADMIN)
    assert detail.release is not None
    assert detail.release.status is UpdateStatus.UNKNOWN
    assert detail.release.failure is CheckFailure.NETWORK


async def test_a_repeat_within_a_minute_answers_from_the_stored_result() -> None:
    """A repeat within a minute answers from the stored result."""
    harness = Harness([release("0.2026.11.0")])
    first = await harness.check().handle(command(), ADMIN)

    again = await harness.check().handle(command(at=NOW + timedelta(seconds=30)), ADMIN)

    assert again == first
    assert len(harness.provider.calls) == 1


async def test_a_later_check_asks_again() -> None:
    """A later check asks again."""
    harness = Harness([release("0.2026.11.0")])
    await harness.check().handle(command(), ADMIN)

    await harness.check().handle(command(at=NOW + timedelta(minutes=2)), ADMIN)

    assert len(harness.provider.calls) == 2


async def test_no_eligible_release_is_not_up_to_date() -> None:
    """No eligible release is not up to date."""
    harness = Harness([release("0.2026.12.0rc1", prerelease=True)])

    outcome = await harness.check().handle(command(), ADMIN)

    assert outcome is not None
    assert outcome.latest is None
    detail = await harness.detail().handle(GetVersionDetailQuery(), ADMIN)
    assert detail.release is not None
    assert detail.release.status is UpdateStatus.NO_RELEASE


async def test_each_channel_keeps_its_own_result() -> None:
    """Each channel keeps its own result."""
    harness = Harness([release("0.2026.11.0"), release("0.2026.12.0rc1")])
    await harness.check().handle(command(channel=ReleaseChannel.STABLE), ADMIN)
    await harness.check().handle(
        command(channel=ReleaseChannel.PREVIEW, at=NOW + timedelta(minutes=2)), ADMIN
    )

    stable = await harness.detail().handle(GetVersionDetailQuery(), ADMIN)
    preview = await harness.detail().handle(
        GetVersionDetailQuery(channel=ReleaseChannel.PREVIEW), ADMIN
    )

    assert stable.release is not None
    assert stable.release.latest is not None
    assert stable.release.latest.version == "0.2026.11.0"
    assert preview.release is not None
    assert preview.release.latest is not None
    assert preview.release.latest.version == "0.2026.12.0rc1"


@pytest.mark.parametrize(
    "repository_url", [None, "https://gitlab.com/o/r", "https://example.com/x/y"]
)
async def test_a_build_without_a_github_repository_has_nothing_to_check(
    repository_url: str | None,
) -> None:
    """A build without a github repository has nothing to check."""
    harness = Harness([release("0.2026.11.0")], repository_url=repository_url)

    assert await harness.check().handle(command(), ADMIN) is None
    detail = await harness.detail().handle(GetVersionDetailQuery(), ADMIN)

    assert detail.release is None
    assert harness.provider.calls == []
    assert not harness.uow.committed
