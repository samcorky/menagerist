"""The search sources for saved fields, example packs and users.

Each source asks the owning module's use case, so what the person may see is the
owner's call: these use the real access guard with real in-memory adapters.
"""

import uuid
from datetime import UTC, datetime

import pytest

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.entrypoints.api.shared.bridges import search_sources
from app.entrypoints.api.shared.bridges.search_sources import (
    ExamplePackSource,
    SavedFieldSource,
    UserSource,
)
from app.modules.examples.adapters.platform.in_memory_pack_catalogue import (
    InMemoryPackCatalogue,
)
from app.modules.examples.application.list_example_packs import ListExamplePacks
from app.modules.examples.domain.pack import ExamplePack
from app.modules.examples.ports.unit_of_work import ExampleRepos
from app.modules.identity.adapters.persistence.in_memory_api_token_repository import (
    InMemoryApiTokenRepository,
)
from app.modules.identity.adapters.persistence.in_memory_device_repository import (
    InMemoryDeviceRepository,
)
from app.modules.identity.adapters.persistence.in_memory_session_repository import (
    InMemorySessionRepository,
)
from app.modules.identity.adapters.persistence.in_memory_sign_in_attempt_repository import (  # noqa: E501
    InMemorySignInAttemptRepository,
)
from app.modules.identity.adapters.persistence.in_memory_user_repository import (
    InMemoryUserRepository,
)
from app.modules.identity.application.list_users import ListUsers
from app.modules.identity.domain.user import Role, User
from app.modules.identity.ports.unit_of_work import IdentityRepos
from app.modules.presets.adapters.persistence.in_memory_preset_repository import (
    InMemoryPresetRepository,
)
from app.modules.presets.application.list_presets import ListPresets
from app.modules.presets.domain.preset import Preset
from app.modules.presets.ports.unit_of_work import PresetRepos
from app.modules.search.domain.search_hit import SearchKind
from app.modules.transfer.adapters.persistence.in_memory_run_repository import (
    InMemoryRunRepository,
)
from app.shared_kernel.actor import Actor
from app.shared_kernel.errors import ForbiddenError

ALICE = Actor(id=uuid.UUID(int=101), roles=frozenset({"member"}))
BOB = Actor(id=uuid.UUID(int=102), roles=frozenset({"member"}))
ADMIN = Actor(id=uuid.UUID(int=100), roles=frozenset({"admin"}))


def _preset(
    owner: uuid.UUID,
    label: str,
    *,
    kind: str = "field",
    description: str | None = None,
) -> Preset:
    return Preset.create(
        owner_id=owner,
        kind=kind,
        label=label,
        description=description,
        definition={"options": ["x"]} if kind == "choice_list" else {},
    )


async def _saved_fields(*presets: Preset) -> SavedFieldSource:
    repos = PresetRepos(presets=InMemoryPresetRepository())
    for preset in presets:
        await repos.presets.add(preset)
    return SavedFieldSource(ListPresets(repos, get_access_guard()))


# --- Saved fields -------------------------------------------------------------


async def test_saved_fields_match_the_name_ignoring_case_and_accents() -> None:
    """Typing without the accent finds the saved field, and says what kind it is."""
    source = await _saved_fields(
        _preset(ALICE.id, "Édition"),
        _preset(ALICE.id, "Grades", kind="choice_list"),
    )

    hits = await source.find("EDITION", 10, ALICE)

    assert [(h.kind, h.title, h.group) for h in hits] == [
        (SearchKind.SAVED_FIELD, "Édition", "field")
    ]


async def test_saved_fields_match_the_description() -> None:
    """A word only in the description still finds the saved field."""
    kept = _preset(
        ALICE.id,
        "Condition",
        kind="choice_list",
        description="Mint, good or poor",
    )
    source = await _saved_fields(kept, _preset(ALICE.id, "Rating"))

    hits = await source.find("mint", 10, ALICE)

    assert [(h.ref, h.description, h.group) for h in hits] == [
        (str(kept.id), "Mint, good or poor", "choice_list")
    ]


async def test_saved_fields_report_the_three_kinds() -> None:
    """A field, a field set and a choice list each carry their own kind."""
    source = await _saved_fields(
        _preset(ALICE.id, "Zed field"),
        _preset(ALICE.id, "Zed set", kind="field_set"),
        _preset(ALICE.id, "Zed list", kind="choice_list"),
    )

    hits = await source.find("zed", 10, ALICE)

    assert {h.title: h.group for h in hits} == {
        "Zed field": "field",
        "Zed set": "field_set",
        "Zed list": "choice_list",
    }


async def test_saved_fields_are_the_callers_own() -> None:
    """Another person's saved fields are never found."""
    source = await _saved_fields(
        _preset(ALICE.id, "Alice only"), _preset(BOB.id, "Bob only")
    )

    assert [h.title for h in await source.find("only", 10, ALICE)] == ["Alice only"]
    assert [h.title for h in await source.find("only", 10, BOB)] == ["Bob only"]


async def test_saved_fields_are_read_in_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    """A match beyond the first page is still found."""
    monkeypatch.setattr(search_sources, "_TYPE_PAGE", 2)
    presets = [_preset(ALICE.id, f"Field {n}") for n in range(5)]
    source = await _saved_fields(*presets)

    hits = await source.find("field", 10, ALICE)

    assert len(hits) == 5


# --- Example packs ------------------------------------------------------------


def _packs() -> ExamplePackSource:
    catalogue = InMemoryPackCatalogue()
    catalogue.add(
        ExamplePack(id="vinyl"), name="Record collection", description="Albums, labels"
    )
    catalogue.add(
        ExamplePack(id="recipes"), name="Recipe box", description="Cooking by course"
    )
    return ExamplePackSource(
        ListExamplePacks(
            ExampleRepos(runs=InMemoryRunRepository()),
            get_access_guard(),
            catalogue,
        )
    )


async def test_example_packs_match_the_name_and_the_description() -> None:
    """Either the pack's name or its description finds it."""
    source = _packs()

    by_name = await source.find("RECORD", 10, ALICE)
    by_description = await source.find("course", 10, ALICE)

    assert [(h.kind, h.ref, h.title) for h in by_name] == [
        (SearchKind.EXAMPLE_PACK, "vinyl", "Record collection")
    ]
    assert [(h.ref, h.description) for h in by_description] == [
        ("recipes", "Cooking by course")
    ]


async def test_example_packs_find_nothing_for_other_words() -> None:
    """A word in neither the name nor the description finds nothing."""
    assert await _packs().find("zeppelin", 10, ALICE) == []


# --- Users --------------------------------------------------------------------


async def _users() -> UserSource:
    repos = IdentityRepos(
        users=InMemoryUserRepository(),
        sessions=InMemorySessionRepository(),
        attempts=InMemorySignInAttemptRepository(),
        tokens=InMemoryApiTokenRepository(),
        devices=InMemoryDeviceRepository(),
    )
    for username, display_name, role in (
        ("alice", "Alice Émile", Role.MEMBER),
        ("jsmith", "Jo Smith", Role.ADMIN),
    ):
        await repos.users.add(
            User.create(
                username=username,
                display_name=display_name,
                password_hash="x",
                role=role,
                now=datetime(2026, 11, 16, tzinfo=UTC),
            )
        )
    return UserSource(ListUsers(repos, get_access_guard()))


async def test_an_administrator_finds_users_by_name_or_username() -> None:
    """The display name (accent-insensitive) and the sign-in name both match."""
    source = await _users()

    by_name = await source.find("emile", 10, ADMIN)
    by_username = await source.find("jsmith", 10, ADMIN)

    assert [(h.kind, h.title, h.description) for h in by_name] == [
        (SearchKind.USER, "Alice Émile", "@alice")
    ]
    assert [h.title for h in by_username] == ["Jo Smith"]


async def test_users_are_for_administrators_only() -> None:
    """A member is refused, so the search leaves the kind out with no hint of it."""
    source = await _users()

    with pytest.raises(ForbiddenError):
        await source.find("alice", 10, ALICE)


async def test_a_user_hit_carries_no_more_than_the_users_page_shows() -> None:
    """A hit holds an id, names and the role; nothing about credentials or locks."""
    source = await _users()

    (found,) = await source.find("alice", 10, ADMIN)

    assert set(vars(found)) == {
        "kind",
        "ref",
        "title",
        "description",
        "group",
        "slug",
        "item_count",
        "attributes",
        "in_collection",
        "score",
    }
    assert found.attributes is None
    assert found.group == "member"
