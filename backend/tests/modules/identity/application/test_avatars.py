import uuid
from typing import TYPE_CHECKING

import pytest

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.modules.identity.adapters.cats.in_memory_cat_picture_source import (
    InMemoryCatPictureSource,
)
from app.modules.identity.adapters.imaging.in_memory_avatar_processor import (
    InMemoryAvatarProcessor,
)
from app.modules.identity.adapters.storage.in_memory_avatar_storage import (
    InMemoryAvatarStorage,
)
from app.modules.identity.application.clear_own_avatar import (
    ClearOwnAvatar,
    ClearOwnAvatarCommand,
)
from app.modules.identity.application.clear_user_avatar import (
    ClearUserAvatar,
    ClearUserAvatarCommand,
)
from app.modules.identity.application.get_user_avatar import (
    GetUserAvatar,
    GetUserAvatarQuery,
)
from app.modules.identity.application.set_own_avatar import (
    SetOwnAvatar,
    SetOwnAvatarCommand,
)
from app.modules.identity.application.set_own_avatar_from_cat_service import (
    SetOwnAvatarFromCatService,
    SetOwnAvatarFromCatServiceCommand,
)
from app.modules.identity.domain.avatar import (
    AVATAR_SIZES,
    MAX_AVATAR_BYTES,
    AvatarSource,
    CropSquare,
)
from app.modules.identity.domain.errors import (
    AvatarNotFoundError,
    CatServiceUnavailableError,
    InvalidAvatarError,
    UserNotFoundError,
)
from app.modules.identity.domain.user import Role, User
from app.modules.identity.ports.unit_of_work import IdentityRepos
from app.shared_kernel.actor import ANONYMOUS_ACTOR, Actor
from app.shared_kernel.errors import ForbiddenError

if TYPE_CHECKING:
    from tests.modules.identity.conftest import MakeUser, World


class Pictures:
    """The picture use cases over one in-memory world."""

    def __init__(self, world: World, cats: list[bytes] | None = None) -> None:
        guard = get_access_guard()
        self.processor = InMemoryAvatarProcessor()
        self.storage = InMemoryAvatarStorage()
        self.set_own = SetOwnAvatar(world.uow, guard, self.processor, self.storage)
        self.cat = SetOwnAvatarFromCatService(
            world.uow,
            guard,
            InMemoryCatPictureSource(cats or []),
            self.processor,
            self.storage,
        )
        self.clear_own = ClearOwnAvatar(world.uow, guard, self.storage)
        self.clear_user = ClearUserAvatar(world.uow, guard, self.storage)
        repos = IdentityRepos(
            users=world.users,
            sessions=world.sessions,
            attempts=world.attempts,
            tokens=world.tokens,
            devices=world.devices,
        )
        self.get = GetUserAvatar(repos, guard, self.storage)


def _actor(user: User) -> Actor:
    return Actor(id=user.id, roles=frozenset({user.role.value}))


async def _stored(world: World, make_user: MakeUser, **kwargs: object) -> User:
    user = make_user(**kwargs)
    await world.users.add(user)
    return user


def _versions(storage: InMemoryAvatarStorage, user: User) -> set[str]:
    return {version for owner, version, _size in storage.files if owner == user.id}


async def test_upload_sets_avatar_and_stores_files(
    world: World, make_user: MakeUser
) -> None:
    """An upload becomes the account's picture, stored at every size."""
    pictures = Pictures(world)
    user = await _stored(world, make_user)

    result = await pictures.set_own.handle(
        SetOwnAvatarCommand(data=b"photo"), _actor(user)
    )

    assert result.avatar is not None
    assert result.avatar.source is AvatarSource.UPLOAD
    stored = await world.users.get(user.id)
    assert stored is not None
    assert stored.avatar == result.avatar
    assert world.uow.committed
    assert {
        size for owner, _v, size in pictures.storage.files if owner == user.id
    } == set(AVATAR_SIZES)


async def test_drawn_source_recorded(world: World, make_user: MakeUser) -> None:
    """A cat drawn in the browser is uploaded and remembered as drawn."""
    pictures = Pictures(world)
    user = await _stored(world, make_user)
    result = await pictures.set_own.handle(
        SetOwnAvatarCommand(data=b"drawn", source=AvatarSource.DRAWN), _actor(user)
    )
    assert result.avatar is not None
    assert result.avatar.source is AvatarSource.DRAWN


async def test_cat_source_refused_on_upload(world: World, make_user: MakeUser) -> None:
    """Only the cat service may record a picture as a cat."""
    pictures = Pictures(world)
    user = await _stored(world, make_user)
    with pytest.raises(InvalidAvatarError):
        await pictures.set_own.handle(
            SetOwnAvatarCommand(data=b"x", source=AvatarSource.CAT), _actor(user)
        )


async def test_too_large_refused(world: World, make_user: MakeUser) -> None:
    """An upload over 5 MB is refused before it is decoded."""
    pictures = Pictures(world)
    user = await _stored(world, make_user)
    with pytest.raises(InvalidAvatarError):
        await pictures.set_own.handle(
            SetOwnAvatarCommand(data=b"x" * (MAX_AVATAR_BYTES + 1)), _actor(user)
        )
    assert pictures.processor.crops == []


async def test_unusable_file_leaves_avatar_unchanged(
    world: World, make_user: MakeUser
) -> None:
    """A file the processor refuses changes nothing."""
    pictures = Pictures(world)
    user = await _stored(world, make_user)
    pictures.processor.fail_next = True
    with pytest.raises(InvalidAvatarError):
        await pictures.set_own.handle(SetOwnAvatarCommand(data=b"x"), _actor(user))
    assert pictures.storage.files == {}


async def test_crop_passed_to_processor(world: World, make_user: MakeUser) -> None:
    """The chosen square reaches the image processor unchanged."""
    pictures = Pictures(world)
    user = await _stored(world, make_user)
    crop = CropSquare(x=4, y=5, size=6)
    await pictures.set_own.handle(
        SetOwnAvatarCommand(data=b"x", crop=crop), _actor(user)
    )
    assert pictures.processor.crops == [crop]


async def test_replacing_deletes_previous_version_files(
    world: World, make_user: MakeUser
) -> None:
    """Only the newest picture's files are kept."""
    pictures = Pictures(world)
    user = await _stored(world, make_user)
    await pictures.set_own.handle(SetOwnAvatarCommand(data=b"one"), _actor(user))
    second = await pictures.set_own.handle(
        SetOwnAvatarCommand(data=b"two"), _actor(user)
    )
    assert second.avatar is not None
    assert _versions(pictures.storage, user) == {second.avatar.version}


async def test_cat_service_sets_cat_source(world: World, make_user: MakeUser) -> None:
    """Random cat stores the service's cat as the picture."""
    pictures = Pictures(world, cats=[b"meow"])
    user = await _stored(world, make_user)
    result = await pictures.cat.handle(
        SetOwnAvatarFromCatServiceCommand(), _actor(user)
    )
    assert result.avatar is not None
    assert result.avatar.source is AvatarSource.CAT
    assert pictures.processor.crops == [None]


async def test_cat_unavailable_leaves_avatar_unchanged(
    world: World, make_user: MakeUser
) -> None:
    """When the service fails, the picture already set stays."""
    pictures = Pictures(world)
    user = await _stored(world, make_user)
    before = await pictures.set_own.handle(
        SetOwnAvatarCommand(data=b"me"), _actor(user)
    )
    with pytest.raises(CatServiceUnavailableError):
        await pictures.cat.handle(SetOwnAvatarFromCatServiceCommand(), _actor(user))
    stored = await world.users.get(user.id)
    assert stored is not None
    assert stored.avatar == before.avatar


async def test_clear_own_removes_files(world: World, make_user: MakeUser) -> None:
    """Use initials clears the picture and its files."""
    pictures = Pictures(world)
    user = await _stored(world, make_user)
    await pictures.set_own.handle(SetOwnAvatarCommand(data=b"me"), _actor(user))
    result = await pictures.clear_own.handle(ClearOwnAvatarCommand(), _actor(user))
    assert result.avatar is None
    assert pictures.storage.files == {}


async def test_admin_clears_someone_else(world: World, make_user: MakeUser) -> None:
    """An administrator can remove another person's picture."""
    pictures = Pictures(world)
    user = await _stored(world, make_user)
    admin = await _stored(world, make_user, username="root", role=Role.ADMIN)
    await pictures.set_own.handle(SetOwnAvatarCommand(data=b"me"), _actor(user))
    result = await pictures.clear_user.handle(
        ClearUserAvatarCommand(user_id=user.id), _actor(admin)
    )
    assert result.avatar is None
    assert pictures.storage.files == {}


async def test_member_cannot_clear_someone_else(
    world: World, make_user: MakeUser
) -> None:
    """Removing someone else's picture is for administrators."""
    pictures = Pictures(world)
    user = await _stored(world, make_user)
    other = await _stored(world, make_user, username="bob")
    with pytest.raises(ForbiddenError):
        await pictures.clear_user.handle(
            ClearUserAvatarCommand(user_id=user.id), _actor(other)
        )


async def test_clearing_a_missing_account_is_not_found(
    world: World, make_user: MakeUser
) -> None:
    """Every write names an account that exists."""
    pictures = Pictures(world)
    admin = await _stored(world, make_user, username="root", role=Role.ADMIN)
    ghost = Actor(id=uuid.uuid7(), roles=frozenset({"member"}))
    with pytest.raises(UserNotFoundError):
        await pictures.clear_user.handle(
            ClearUserAvatarCommand(user_id=uuid.uuid7()), _actor(admin)
        )
    with pytest.raises(UserNotFoundError):
        await pictures.clear_own.handle(ClearOwnAvatarCommand(), ghost)
    with pytest.raises(UserNotFoundError):
        await pictures.set_own.handle(SetOwnAvatarCommand(data=b"x"), ghost)


async def test_token_actor_cannot_set_own(world: World, make_user: MakeUser) -> None:
    """Pictures are changed by a signed-in person, not an API token."""
    pictures = Pictures(world)
    user = await _stored(world, make_user)
    token = Actor(id=user.id, roles=frozenset({"member"}), grants=frozenset())
    with pytest.raises(ForbiddenError):
        await pictures.set_own.handle(SetOwnAvatarCommand(data=b"x"), token)


async def test_get_returns_bytes_for_current_version(
    world: World, make_user: MakeUser
) -> None:
    """Any signed-in member can load someone's current picture."""
    pictures = Pictures(world)
    user = await _stored(world, make_user)
    viewer = await _stored(world, make_user, username="bob")
    result = await pictures.set_own.handle(
        SetOwnAvatarCommand(data=b"me"), _actor(user)
    )
    assert result.avatar is not None
    data = await pictures.get.handle(
        GetUserAvatarQuery(user_id=user.id, version=result.avatar.version, size=128),
        _actor(viewer),
    )
    assert data == f"{result.avatar.version}-128".encode()


async def test_get_wrong_version_not_found(world: World, make_user: MakeUser) -> None:
    """An old version's address stops working once the picture changes."""
    pictures = Pictures(world)
    user = await _stored(world, make_user)
    first = await pictures.set_own.handle(
        SetOwnAvatarCommand(data=b"one"), _actor(user)
    )
    assert first.avatar is not None
    old_version = first.avatar.version
    await pictures.set_own.handle(SetOwnAvatarCommand(data=b"two"), _actor(user))
    with pytest.raises(AvatarNotFoundError):
        await pictures.get.handle(
            GetUserAvatarQuery(user_id=user.id, version=old_version, size=64),
            _actor(user),
        )


async def test_get_unknown_size_not_found(world: World, make_user: MakeUser) -> None:
    """Only the stored sizes can be asked for."""
    pictures = Pictures(world)
    user = await _stored(world, make_user)
    result = await pictures.set_own.handle(
        SetOwnAvatarCommand(data=b"me"), _actor(user)
    )
    assert result.avatar is not None
    with pytest.raises(AvatarNotFoundError):
        await pictures.get.handle(
            GetUserAvatarQuery(user_id=user.id, version=result.avatar.version, size=99),
            _actor(user),
        )


async def test_get_missing_file_not_found(world: World, make_user: MakeUser) -> None:
    """A picture whose files went missing is not found rather than an error."""
    pictures = Pictures(world)
    user = await _stored(world, make_user)
    result = await pictures.set_own.handle(
        SetOwnAvatarCommand(data=b"me"), _actor(user)
    )
    assert result.avatar is not None
    pictures.storage.files.clear()
    with pytest.raises(AvatarNotFoundError):
        await pictures.get.handle(
            GetUserAvatarQuery(user_id=user.id, version=result.avatar.version, size=64),
            _actor(user),
        )


async def test_get_no_avatar_not_found(world: World, make_user: MakeUser) -> None:
    """An account showing its initials has no picture to load."""
    pictures = Pictures(world)
    user = await _stored(world, make_user)
    with pytest.raises(AvatarNotFoundError):
        await pictures.get.handle(
            GetUserAvatarQuery(user_id=user.id, version="0" * 16, size=64), _actor(user)
        )
    with pytest.raises(AvatarNotFoundError):
        await pictures.get.handle(
            GetUserAvatarQuery(user_id=uuid.uuid7(), version="0" * 16, size=64),
            _actor(user),
        )


async def test_anonymous_cannot_get(world: World, make_user: MakeUser) -> None:
    """Pictures are only for signed-in people."""
    pictures = Pictures(world)
    user = await _stored(world, make_user)
    with pytest.raises(ForbiddenError):
        await pictures.get.handle(
            GetUserAvatarQuery(user_id=user.id, version="0" * 16, size=64),
            ANONYMOUS_ACTOR,
        )


async def test_undecodable_cat_counts_as_unavailable(
    world: World, make_user: MakeUser
) -> None:
    """A reply that is not a usable picture falls back like an unreachable service."""
    pictures = Pictures(world, cats=[b"not really a cat"])
    user = await _stored(world, make_user)
    pictures.processor.fail_next = True
    with pytest.raises(CatServiceUnavailableError):
        await pictures.cat.handle(SetOwnAvatarFromCatServiceCommand(), _actor(user))
    assert pictures.storage.files == {}


async def test_files_written_under_the_row_lock(
    world: World, make_user: MakeUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two writes for one person queue on the row lock and keep each other's files."""
    pictures = Pictures(world)
    user = await _stored(world, make_user)
    events: list[str] = []
    locked = world.users.get_for_update
    saved = pictures.storage.save
    removed = pictures.storage.remove

    async def lock(user_id: uuid.UUID) -> User | None:
        events.append("lock")
        return await locked(user_id)

    async def save(*args: object, **kwargs: object) -> None:
        events.append("save")
        await saved(*args, **kwargs)  # type: ignore[arg-type]

    async def remove(*args: object, **kwargs: object) -> None:
        events.append("remove")
        await removed(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(world.users, "get_for_update", lock)
    monkeypatch.setattr(pictures.storage, "save", save)
    monkeypatch.setattr(pictures.storage, "remove", remove)

    await pictures.set_own.handle(SetOwnAvatarCommand(data=b"me"), _actor(user))

    assert events == ["lock", "save", "remove"]


async def test_failed_commit_removes_its_own_files_only(
    world: World, make_user: MakeUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A write that does not commit leaves the earlier picture and no stray files."""
    pictures = Pictures(world)
    user = await _stored(world, make_user)
    first = await pictures.set_own.handle(
        SetOwnAvatarCommand(data=b"one"), _actor(user)
    )
    assert first.avatar is not None
    kept = first.avatar.version

    async def broken() -> None:
        raise RuntimeError("database went away")

    monkeypatch.setattr(world.uow, "commit", broken)
    with pytest.raises(RuntimeError):
        await pictures.set_own.handle(SetOwnAvatarCommand(data=b"two"), _actor(user))

    assert _versions(pictures.storage, user) == {kept}


async def test_cleanup_failure_does_not_fail_the_change(
    world: World, make_user: MakeUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Old files that cannot be removed yet are logged, not reported as a failure."""
    pictures = Pictures(world)
    user = await _stored(world, make_user)

    async def stuck(*_args: object, **_kwargs: object) -> None:
        raise PermissionError("file in use")

    monkeypatch.setattr(pictures.storage, "remove", stuck)
    result = await pictures.set_own.handle(
        SetOwnAvatarCommand(data=b"me"), _actor(user)
    )
    assert result.avatar is not None
    cleared = await pictures.clear_own.handle(ClearOwnAvatarCommand(), _actor(user))
    assert cleared.avatar is None


async def test_get_without_bytes_checks_but_does_not_read(
    world: World, make_user: MakeUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A revalidation is checked like a load but never touches the disk."""
    pictures = Pictures(world)
    user = await _stored(world, make_user)
    result = await pictures.set_own.handle(
        SetOwnAvatarCommand(data=b"me"), _actor(user)
    )
    assert result.avatar is not None
    version = result.avatar.version

    async def no_reads(*_args: object) -> bytes | None:
        raise AssertionError("read the file")

    monkeypatch.setattr(pictures.storage, "read", no_reads)
    query = GetUserAvatarQuery(
        user_id=user.id, version=version, size=64, include_bytes=False
    )
    assert await pictures.get.handle(query, _actor(user)) == b""
    with pytest.raises(AvatarNotFoundError):
        await pictures.get.handle(
            GetUserAvatarQuery(
                user_id=user.id, version="0" * 16, size=64, include_bytes=False
            ),
            _actor(user),
        )
