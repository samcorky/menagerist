import uuid
from typing import TYPE_CHECKING, Any

import pytest

from app.modules.presets.application.list_presets import ListPresets, ListPresetsQuery
from app.modules.presets.domain.errors import PresetNotFoundError
from app.modules.transfer.adapters.codecs.menagerist_bundle import MenageristBundleCodec
from app.modules.transfer.application.bundle_files import (
    BundleFileRequest,
    ExportBundle,
    ExportBundleQuery,
    ImportBundle,
    PlanBundleImport,
)
from app.modules.transfer.application.codecs import CodecRegistry
from app.modules.transfer.domain.entity_kind import EntityKind
from app.modules.transfer.domain.errors import UnknownFormatError
from app.modules.transfer.domain.plan import PlanAction
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import Actor

if TYPE_CHECKING:
    from tests.modules.conftest import Shared

ALICE = Actor(id=uuid.UUID(int=0xA1), roles=frozenset({"member"}))
BOB = Actor(id=uuid.UUID(int=0xB2), roles=frozenset({"member"}))
GUARD = InMemoryAccessGuard()
CODECS = CodecRegistry([MenageristBundleCodec()])
FILE: dict[str, Any] = {
    "format": "menagerist-bundle",
    "version": 1,
    "presets": [
        {
            "ref": "grades",
            "kind": "choice_list",
            "label": "Grades",
            "definition": {"options": ["Mint", "Good"]},
        }
    ],
}


def _plan(shared: Shared, actor: Actor) -> PlanBundleImport:
    t = shared.targets(actor)
    return PlanBundleImport(GUARD, CODECS, t.presets, t.graph, t.collections)


def _import(shared: Shared, actor: Actor) -> ImportBundle:
    t = shared.targets(actor)
    return ImportBundle(GUARD, CODECS, t.presets, t.graph, t.collections)


def _export(shared: Shared, actor: Actor) -> ExportBundle:
    t = shared.targets(actor)
    return ExportBundle(GUARD, CODECS, t.presets, t.graph, t.collections)


async def _ids(shared: Shared, actor: Actor) -> list[uuid.UUID]:
    presets = await ListPresets(shared.preset_repos, GUARD).handle(
        ListPresetsQuery(), actor
    )
    return [p.id for p in presets]


async def test_planning_writes_nothing_and_importing_follows_it(
    shared: Shared,
) -> None:
    """The dry run says `create`; importing creates it; then it is `unchanged`."""
    request = BundleFileRequest(data=FILE)

    before = await _plan(shared, ALICE).handle(request, ALICE)
    again = await _plan(shared, ALICE).handle(request, ALICE)
    applied = await _import(shared, ALICE).handle(request, ALICE)
    after = await _plan(shared, ALICE).handle(request, ALICE)

    assert [e.action for e in before.entities] == [PlanAction.CREATE]
    assert [e.action for e in again.entities] == [PlanAction.CREATE]
    assert applied.created[EntityKind.PRESET] == 1
    assert [e.action for e in after.entities] == [PlanAction.UNCHANGED]


async def test_an_export_names_presets_by_id_and_imports_as_unchanged(
    shared: Shared,
) -> None:
    """An exported file uses each preset's id as its ref, and imports cleanly."""
    await _import(shared, ALICE).handle(BundleFileRequest(data=FILE), ALICE)
    ids = await _ids(shared, ALICE)

    exported = await _export(shared, ALICE).handle(
        ExportBundleQuery(preset_ids=ids), ALICE
    )
    plan = await _plan(shared, ALICE).handle(BundleFileRequest(data=exported), ALICE)

    assert exported["format"] == "menagerist-bundle"
    assert [p["ref"] for p in exported["presets"]] == [str(i) for i in ids]
    assert [p["label"] for p in exported["presets"]] == ["Grades"]
    assert [e.action for e in plan.entities] == [PlanAction.UNCHANGED]


async def test_another_persons_preset_cannot_be_exported(shared: Shared) -> None:
    """Bob exporting Alice's preset reads as a missing one."""
    await _import(shared, ALICE).handle(BundleFileRequest(data=FILE), ALICE)
    ids = await _ids(shared, ALICE)

    with pytest.raises(PresetNotFoundError):
        await _export(shared, BOB).handle(ExportBundleQuery(preset_ids=ids), BOB)


async def test_an_unknown_format_is_refused_both_ways(shared: Shared) -> None:
    """No codec for the format refuses the import and the export."""
    with pytest.raises(UnknownFormatError):
        await _plan(shared, ALICE).handle(
            BundleFileRequest(data={**FILE, "format": "menagerist-presets"}), ALICE
        )
    with pytest.raises(UnknownFormatError):
        await _export(shared, ALICE).handle(
            ExportBundleQuery(preset_ids=[uuid.uuid7()], format="csv"), ALICE
        )
