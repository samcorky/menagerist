"""Plan a bundle against what the person has, then apply that plan through targets.

Every source goes through here: a decoded file, a catalogue entry, an example pack.
Planning reads only, so the same plan is a dry run and, applied, what the import
does. What only some sources need travels in `BundleExtras`.
"""

from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from app.modules.transfer.application.content_hash import item_field_hashes, preset_key
from app.modules.transfer.application.extras import (
    Adoption,
    BundleExtras,
    Key,
    connection_ref,
)
from app.modules.transfer.domain.bundle import BundleSource, split_ref
from app.modules.transfer.domain.entity_kind import EntityKind
from app.modules.transfer.domain.errors import BundleConflictError, InvalidBundleError
from app.modules.transfer.domain.plan import (
    ClashPolicy,
    Plan,
    PlanAction,
    PlanBlocker,
    PlannedEntity,
)
from app.modules.transfer.domain.source_link import SourceLink
from app.modules.transfer.ports.source_link_repository import SourceLinkRepository
from app.shared_kernel.content_filter import ContentFilter

if TYPE_CHECKING:
    import uuid
    from collections.abc import Sequence

    from app.modules.transfer.domain.bundle import Bundle, BundleItem
    from app.modules.transfer.ports.targets import (
        Created,
        GraphTarget,
        PresetOutcome,
        PresetTarget,
    )

_PRESET_EXISTS = "You already have one the same."
_NAME_TAKEN = "You already have one with this name."
_TAKEN_BACK = "Kept from an earlier install, and taken back as it is."
_NOUNS = {
    EntityKind.ITEM_TYPE: "an item type",
    EntityKind.RELATIONSHIP_TYPE: "a relationship type",
}
# Counted even when a bundle holds none; the other kinds only when it holds some.
_ALWAYS_COUNTED = (
    EntityKind.PRESET,
    EntityKind.RELATIONSHIP_TYPE,
    EntityKind.ITEM_TYPE,
)


@dataclass(kw_only=True, frozen=True, eq=False)
class AppliedBundle:
    """What applying a plan created, and what it left as the person had it."""

    bundle_id: str
    created: dict[EntityKind, int] = field(default_factory=dict)
    skipped: dict[EntityKind, int] = field(default_factory=dict)

    @property
    def total_created(self) -> int:
        """Everything created, of every kind."""
        return sum(self.created.values())

    @property
    def total_skipped(self) -> int:
        """Everything left as it was, of every kind."""
        return sum(self.skipped.values())


async def plan_bundle(
    bundle: Bundle,
    presets: PresetTarget,
    graph: GraphTarget,
    *,
    clash: ClashPolicy,
    extras: BundleExtras | None = None,
) -> Plan:
    """Work out what applying `bundle` would do, without writing anything.

    A preset is `unchanged` when the person has an identical one or it repeats one
    earlier in the bundle. A type whose name is taken is `unchanged` or a conflict,
    as `clash` says. The presets are checked first, so a bundle that applying would
    refuse is refused here too. Entities come in apply order: presets, types, items,
    connections, collections, covers.

    Raises:
        ValidationError: a preset is malformed, or there are too many.
    """
    extras = extras or BundleExtras()
    await presets.check(bundle.presets)
    planner = _Planner(bundle, extras)
    planner.presets(await presets.existing(bundle.presets))
    await planner.types(graph, clash)
    await planner.items(graph)
    await planner.items_fit(graph)
    planner.connections()
    planner.collections()
    await planner.covers()
    return Plan(
        bundle_id=bundle.id,
        entities=tuple(planner.entities),
        blockers=(*extras.blockers, *planner.blockers),
    )


def _fields_used(items: Sequence[BundleItem], type_ref: str) -> set[str]:
    """The field keys the items of a type fill in, apart from fields only they have."""
    used: set[str] = set()
    for item in items:
        if item.type_ref == type_ref:
            own = (item.extra_schema or {}).get("properties", {})
            used |= {key for key in item.attributes if key not in own}
    return used


@dataclass(kw_only=True, frozen=True, eq=False)
class _Keyed:
    """What planning needs to link a bundle's items to their source keys."""

    source: BundleSource
    links: SourceLinkRepository
    scope: ContentFilter
    counts: Counter[str | None]


def _key_value(spec: BundleItem, key_field: str) -> str | None:
    """The text of the item's `key_field` that finds a hand-made item, if it has one.

    A number is read as its text. A blank or non-text value finds nothing.
    """
    value: object = spec.name if key_field == "name" else spec.attributes.get(key_field)
    if isinstance(value, bool) or not isinstance(value, str | int | float):
        return None
    text = str(value)
    return text if text.strip() else None


class _Planner:
    """Decides each entity in apply order, so later kinds see earlier choices."""

    def __init__(self, bundle: Bundle, extras: BundleExtras) -> None:
        self._bundle = bundle
        self._extras = extras
        self.entities: list[PlannedEntity] = []
        self.blockers: list[PlanBlocker] = []
        # Item types the file names whose slug the person already uses: ref to slug.
        self._reused_types: dict[str, str] = {}
        self._taken_back: set[Key] = set()
        # Items applying leaves as they are, and the ones whose key is ambiguous.
        self._not_created: set[str] = set()
        self._ambiguous_refs: set[str] = set()
        # Item ids and names known before anything is created: adopted and external.
        self._item_ids: dict[str, uuid.UUID] = {}
        self._item_names: dict[str, str] = {}
        for (kind, pack_id, ref), found in extras.external.items():
            if kind is EntityKind.ITEM:
                self._item_ids[f"{pack_id}:{ref}"] = found.entity_id
                self._item_names[f"{pack_id}:{ref}"] = cast("str", found.name)

    def _add(
        self,
        kind: EntityKind,
        ref: str,
        label: str,
        action: PlanAction,
        reason: str | None = None,
    ) -> None:
        self.entities.append(
            PlannedEntity(kind=kind, ref=ref, label=label, action=action, reason=reason)
        )

    def _unchanged_or_create(
        self, kind: EntityKind, ref: str, label: str, reason: str | None
    ) -> None:
        action = PlanAction.CREATE if reason is None else PlanAction.UNCHANGED
        self._add(kind, ref, label, action, reason)

    def _take_back(self, kind: EntityKind, ref: str, label: str) -> Adoption | None:
        """Plan to take back what an earlier install kept, if there is one."""
        adoption = self._extras.adoptions.get((kind, ref))
        if adoption is None:
            return None
        self._add(kind, ref, label, PlanAction.UNCHANGED, _TAKEN_BACK)
        self._taken_back.add((kind, ref))
        return adoption

    def presets(self, existing: list[bool]) -> None:
        """An identical preset the person has, or repeats, is used, not created."""
        first: dict[str, str] = {}
        for spec, exists in zip(self._bundle.presets, existing, strict=True):
            key = preset_key(spec.kind, spec.label, spec.definition)
            reason: str | None = None
            if exists:
                reason = _PRESET_EXISTS
            elif key in first:
                reason = f"The same as '{first[key]}', earlier in this file."
            else:
                first[key] = spec.ref
            self._unchanged_or_create(EntityKind.PRESET, spec.ref, spec.label, reason)

    async def types(self, graph: GraphTarget, clash: ClashPolicy) -> None:
        """Plan the relationship and item types; a taken slug is `clash`'s to say."""
        for kind, specs in (
            (EntityKind.RELATIONSHIP_TYPE, self._bundle.relationship_types),
            (EntityKind.ITEM_TYPE, self._bundle.item_types),
        ):
            for spec in specs:
                if self._take_back(kind, spec.ref, spec.label) is not None:
                    continue
                taken = await graph.slug_taken(kind, spec.slug)
                self._type(kind, spec.ref, spec.label, spec.slug, taken, clash)
                if taken and kind is EntityKind.ITEM_TYPE and clash is ClashPolicy.SKIP:
                    self._reused_types[spec.ref] = spec.slug

    def _type(
        self,
        kind: EntityKind,
        ref: str,
        label: str,
        slug: str,
        taken: bool,
        clash: ClashPolicy,
    ) -> None:
        if not taken:
            self._add(kind, ref, label, PlanAction.CREATE)
        elif clash is ClashPolicy.SKIP:
            self._add(kind, ref, label, PlanAction.UNCHANGED, _NAME_TAKEN)
        else:
            reason = (
                f"You already have {_NOUNS[kind]} called '{slug}'. "
                + "Rename or remove it, then try again."
            )
            self._add(kind, ref, label, PlanAction.CONFLICT, reason)

    async def items(self, graph: GraphTarget) -> None:
        """Plan each item: taken back, linked to its source key, or created.

        An item with a source key is `unchanged` when an earlier import made it or a
        hand-made item has its key field's value, and `ambiguous` when its key
        names more than one item.
        """
        keyed = self._keyed_items()
        for spec in self._bundle.items:
            adoption = self._take_back(EntityKind.ITEM, spec.ref, spec.name)
            if adoption is not None:
                self._item_ids[spec.ref] = adoption.record.entity_id
                self._item_names[spec.ref] = adoption.content["name"]
                continue
            self._item_names[spec.ref] = spec.name
            if keyed is None or spec.source_key is None:
                self._add(EntityKind.ITEM, spec.ref, spec.name, PlanAction.CREATE)
            else:
                await self._keyed_item(spec, keyed, graph)

    def _keyed_items(self) -> _Keyed | None:
        """Return what planning needs to link items, or `None` if it cannot."""
        source = self._bundle.source
        links = self._extras.links
        owner_id = self._extras.owner_id
        if source is None or links is None or owner_id is None:
            return None
        return _Keyed(
            source=source,
            links=links,
            scope=ContentFilter.of(owner_id),
            counts=Counter(i.source_key for i in self._bundle.items if i.source_key),
        )

    async def _keyed_item(
        self, spec: BundleItem, keyed: _Keyed, graph: GraphTarget
    ) -> None:
        key = cast("str", spec.source_key)
        ref, name = spec.ref, spec.name
        if keyed.counts[key] > 1:
            self._ambiguous(
                ref, name, f"Another row in this file has the same key '{key}'."
            )
            return
        link = await keyed.links.get_by_key(
            keyed.source.name, EntityKind.ITEM, key, scope=keyed.scope
        )
        if link is not None and await graph.inspect(EntityKind.ITEM, link.entity_id):
            self._extras.linked[ref] = self._item_ids[ref] = link.entity_id
            self._skip(ref, name, f"Already imported from {keyed.source.name}.")
            return
        # No link, or one whose item has gone: look for an item the person made.
        field = keyed.source.key_field
        slug = self._item_type_slug(spec.type_ref)
        value = _key_value(spec, field) if field is not None else None
        if field is None or slug is None or value is None:
            self._add(EntityKind.ITEM, ref, name, PlanAction.CREATE)
            return
        found = await graph.find_items_by_field(slug, field, value)
        if len(found) > 1:
            self._ambiguous(
                ref,
                name,
                f"More than one of your items has {field} '{value}'. "
                + "Make it unique, then try again.",
            )
        elif found:
            self._extras.matched[ref] = self._item_ids[ref] = found[0]
            self._skip(
                ref,
                name,
                "Matches your existing item. It will be linked, not changed.",
            )
        else:
            self._add(EntityKind.ITEM, ref, name, PlanAction.CREATE)

    def _skip(self, ref: str, name: str, reason: str) -> None:
        self._not_created.add(ref)
        self._add(EntityKind.ITEM, ref, name, PlanAction.UNCHANGED, reason)

    def _ambiguous(self, ref: str, name: str, reason: str) -> None:
        self._not_created.add(ref)
        self._ambiguous_refs.add(ref)
        self._add(EntityKind.ITEM, ref, name, PlanAction.AMBIGUOUS, reason)

    def _item_type_slug(self, type_ref: str | None) -> str | None:
        """The slug of the item type `type_ref`, in this bundle or a required pack."""
        if type_ref is None:
            return None
        for spec in self._bundle.item_types:
            if spec.ref == type_ref:
                return spec.slug
        pack_id, local = split_ref(type_ref)
        found = self._extras.external.get((EntityKind.ITEM_TYPE, pack_id or "", local))
        return None if found is None else found.slug

    async def items_fit(self, graph: GraphTarget) -> None:
        """Block when items would go under a type the person has that lacks a field.

        A taken slug keeps the person's own type. Items written for a type with other
        fields would be refused part-way through applying, so the plan says so first.
        """
        for ref, slug in self._reused_types.items():
            used = _fields_used(self._bundle.items, ref)
            if not used:
                continue
            have = await graph.item_type_field_keys(slug) or frozenset()
            missing = sorted(used - have)
            if missing:
                self.blockers.append(
                    PlanBlocker(
                        code="ItemTypeMismatchError",
                        reason=(
                            f"You already have an item type called '{slug}', and it "
                            + f"has no field {', '.join(repr(k) for k in missing)} "
                            + "that items in this file use."
                        ),
                    )
                )

    def connections(self) -> None:
        """A kept connection is taken back only if it still joins the same items."""
        for n, spec in enumerate(self._bundle.connections):
            ref = connection_ref(n)
            # A required pack's item has no name here when that pack is missing.
            source = self._item_names.get(spec.source_ref, spec.source_ref)
            target = self._item_names.get(spec.target_ref, spec.target_ref)
            label = f"{source} to {target}"
            if {spec.source_ref, spec.target_ref} & self._ambiguous_refs:
                reason = "Left out: an item it joins has an ambiguous key."
                self._add(
                    EntityKind.CONNECTION, ref, label, PlanAction.UNCHANGED, reason
                )
                continue
            kept = self._extras.adoptions.get((EntityKind.CONNECTION, ref))
            source_id = self._item_ids.get(spec.source_ref)
            target_id = self._item_ids.get(spec.target_ref)
            if (
                kept is not None
                and kept.content["source_id"] == str(source_id)
                and kept.content["target_id"] == str(target_id)
            ):
                self._take_back(EntityKind.CONNECTION, ref, label)
            else:
                self._add(EntityKind.CONNECTION, ref, label, PlanAction.CREATE)

    def collections(self) -> None:
        """Plan each collection, taking back one an earlier install kept."""
        for spec in self._bundle.collections:
            if self._take_back(EntityKind.COLLECTION, spec.ref, spec.name) is None:
                self._add(EntityKind.COLLECTION, spec.ref, spec.name, PlanAction.CREATE)

    async def covers(self) -> None:
        """Plan a cover for each item whose type has a style.

        A kept cover comes back only with its adopted item, and an adopted item that
        already has a cover of the person's own gets none, so it is not listed.
        """
        covers = self._extras.covers
        styles = self._extras.cover_styles
        for spec in self._bundle.items:
            if covers is None or spec.type_ref is None or spec.type_ref not in styles:
                continue
            if spec.ref in self._not_created:
                continue
            name = self._item_names[spec.ref]
            if (EntityKind.ITEM, spec.ref) in self._taken_back:
                if self._take_back(EntityKind.COVER, spec.ref, name) is not None:
                    continue
                if await covers.has_cover(self._item_ids[spec.ref]):
                    continue
            self._add(EntityKind.COVER, spec.ref, name, PlanAction.CREATE)


async def apply_bundle(
    plan: Plan,
    bundle: Bundle,
    presets: PresetTarget,
    graph: GraphTarget,
    *,
    extras: BundleExtras | None = None,
) -> AppliedBundle:
    """Create what `plan` marks `create`, through the targets, in plan order.

    The presets are ensured as one batch, so a type's `$preset` markers resolve to
    the person's existing copy as well as a new one; the target creates only those
    the plan marks `create`, as it uses the same notion of "the same". What the plan
    takes back is recorded in the ledger, if there is one, instead of created.

    Raises:
        BundleConflictError: the plan has a conflict or a blocker.
    """
    if not plan.ready:
        problem = (
            plan.conflicts[0].reason if plan.conflicts else plan.blockers[0].reason
        )
        raise BundleConflictError(problem or "The bundle cannot be applied.")
    applier = _Applier(plan, bundle, graph, extras or BundleExtras())
    outcomes = await presets.ensure(bundle.presets)
    await applier.presets(outcomes)
    await applier.relationship_types()
    await applier.item_types()
    await applier.items()
    await applier.connections()
    await applier.collections()
    await applier.covers()
    return applier.result()


class _Applier:
    """Applies a plan one kind at a time, remembering what later kinds refer to."""

    def __init__(
        self, plan: Plan, bundle: Bundle, graph: GraphTarget, extras: BundleExtras
    ) -> None:
        self._plan = plan
        self._bundle = bundle
        self._graph = graph
        self._extras = extras
        self._created: Counter[EntityKind] = Counter()
        self._ambiguous = {
            e.ref
            for e in plan.entities
            if e.kind is EntityKind.ITEM and e.action is PlanAction.AMBIGUOUS
        }
        self._preset_ids: dict[str, uuid.UUID] = {}
        self._type_slugs: dict[str, str] = {}
        self._relationship_slugs: dict[str, str] = {}
        self._item_ids: dict[str, uuid.UUID] = {}
        self._item_names: dict[str, str] = {}
        for (kind, pack_id, ref), found in extras.external.items():
            key = f"{pack_id}:{ref}"
            if kind is EntityKind.ITEM_TYPE:
                self._type_slugs[key] = cast("str", found.slug)
            elif kind is EntityKind.RELATIONSHIP_TYPE:
                self._relationship_slugs[key] = cast("str", found.slug)
            else:
                self._item_ids[key] = found.entity_id
                self._item_names[key] = cast("str", found.name)

    def _action(self, kind: EntityKind, ref: str) -> PlanAction | None:
        return next(
            (e.action for e in self._plan.entities if (e.kind, e.ref) == (kind, ref)),
            None,
        )

    def _adoption(self, kind: EntityKind, ref: str) -> Adoption | None:
        """The kept entity the plan takes back for `kind` and `ref`, if any."""
        if self._action(kind, ref) is not PlanAction.UNCHANGED:
            return None
        key: Key = (kind, ref)
        return self._extras.adoptions.get(key)

    def _creating(self, kind: EntityKind, ref: str) -> bool:
        return self._action(kind, ref) is PlanAction.CREATE

    async def _made(
        self, kind: EntityKind, ref: str, label: str, created: Created
    ) -> None:
        self._created[kind] += 1
        if self._extras.ledger is not None:
            await self._extras.ledger.created(kind, ref, label, created)

    async def _took_back(self, adoption: Adoption, ref: str, label: str) -> None:
        if self._extras.ledger is not None:
            await self._extras.ledger.adopted(adoption, ref, label)

    async def presets(self, outcomes: list[PresetOutcome]) -> None:
        """Resolve every preset marker, and record the presets that were created."""
        self._preset_ids = {o.ref: o.entity_id for o in outcomes}
        self._created[EntityKind.PRESET] = sum(1 for o in outcomes if o.created)
        if self._extras.ledger is not None:
            await self._extras.ledger.presets(outcomes, self._bundle.presets)

    async def relationship_types(self) -> None:
        """Create the relationship types the plan marks `create`."""
        for spec in self._bundle.relationship_types:
            self._relationship_slugs[spec.ref] = spec.slug
            kind = EntityKind.RELATIONSHIP_TYPE
            if (adoption := self._adoption(kind, spec.ref)) is not None:
                await self._took_back(adoption, spec.ref, spec.label)
            elif self._creating(kind, spec.ref):
                created = await self._graph.create_relationship_type(
                    spec, self._preset_ids
                )
                await self._made(kind, spec.ref, spec.label, created)

    async def item_types(self) -> None:
        """Create the item types the plan marks `create`."""
        for spec in self._bundle.item_types:
            self._type_slugs[spec.ref] = spec.slug
            kind = EntityKind.ITEM_TYPE
            if (adoption := self._adoption(kind, spec.ref)) is not None:
                await self._took_back(adoption, spec.ref, spec.label)
            elif self._creating(kind, spec.ref):
                created = await self._graph.create_item_type(spec, self._preset_ids)
                await self._made(kind, spec.ref, spec.label, created)

    async def items(self) -> None:
        """Create the items, or take back the ones an earlier install kept."""
        for spec in self._bundle.items:
            kind = EntityKind.ITEM
            if (adoption := self._adoption(kind, spec.ref)) is not None:
                self._item_ids[spec.ref] = adoption.record.entity_id
                self._item_names[spec.ref] = adoption.content["name"]
                await self._took_back(adoption, spec.ref, spec.name)
                continue
            if spec.ref in self._ambiguous:
                continue
            existing = self._extras.linked.get(spec.ref)
            matched = self._extras.matched.get(spec.ref)
            if existing is not None or matched is not None:
                # Made by an earlier import, or by the person: as they have it.
                self._item_ids[spec.ref] = cast("uuid.UUID", existing or matched)
                self._item_names[spec.ref] = spec.name
                if matched is not None:
                    await self._link(spec, matched)
                continue
            if self._action(kind, spec.ref) is PlanAction.UNCHANGED:
                continue  # left as it is; these extras did not plan it
            type_ref = spec.type_ref
            type_slug = self._type_slugs[type_ref] if type_ref else None
            created = await self._graph.create_item(spec, type_slug=type_slug)
            self._item_ids[spec.ref] = created.entity_id
            self._item_names[spec.ref] = spec.name
            await self._made(kind, spec.ref, spec.name, created)
            await self._link(spec, created.entity_id)

    async def _link(self, spec: BundleItem, entity_id: uuid.UUID) -> None:
        """Link the item to its source key, re-pointing a link whose item had gone."""
        source = self._bundle.source
        links = self._extras.links
        owner_id = self._extras.owner_id
        if source is None or links is None or owner_id is None:
            return
        if spec.source_key is None:
            return
        fields = item_field_hashes(spec)
        scope = ContentFilter.of(owner_id)
        link = await links.get_by_key(
            source.name, EntityKind.ITEM, spec.source_key, scope=scope
        )
        if link is None:
            await links.add(
                SourceLink.create(
                    owner_id=owner_id,
                    source=source.name,
                    kind=EntityKind.ITEM,
                    key=spec.source_key,
                    entity_id=entity_id,
                    fields=fields,
                )
            )
        else:
            link.record_import(entity_id, fields)
            await links.save(link)

    async def connections(self) -> None:
        """Create the connections, or take back the ones that still join the same."""
        for n, spec in enumerate(self._bundle.connections):
            if {spec.source_ref, spec.target_ref} & self._ambiguous:
                continue
            source = self._item_names[spec.source_ref]
            target = self._item_names[spec.target_ref]
            ref = connection_ref(n)
            label = f"{source} to {target}"
            # The plan takes it back only if it still joins the same items.
            if (adoption := self._adoption(EntityKind.CONNECTION, ref)) is not None:
                await self._took_back(adoption, ref, label)
                continue
            created = await self._graph.create_connection(
                spec,
                source_id=self._item_ids[spec.source_ref],
                target_id=self._item_ids[spec.target_ref],
                type_slug=self._relationship_slugs[spec.type_ref],
            )
            await self._made(EntityKind.CONNECTION, ref, label, created)

    async def collections(self) -> None:
        """Create the collections, or take back the ones an earlier install kept."""
        for spec in self._bundle.collections:
            refs = [r for r in spec.item_refs if r not in self._ambiguous]
            if spec.item_refs and not refs:
                continue
            missing = [ref for ref in refs if ref not in self._item_ids]
            if missing:
                raise InvalidBundleError(
                    f"Collection '{spec.name}' names items that were not created: "
                    + ", ".join(missing)
                )
            kind = EntityKind.COLLECTION
            if (adoption := self._adoption(kind, spec.ref)) is not None:
                await self._took_back(adoption, spec.ref, spec.name)
                continue
            target = self._extras.collections
            if target is None:
                raise InvalidBundleError("This source cannot make collections.")
            created = await target.create_collection(
                spec, item_ids=[self._item_ids[ref] for ref in refs]
            )
            await self._made(kind, spec.ref, spec.name, created)

    async def covers(self) -> None:
        """Give every item the plan lists a cover its type's style draws.

        Last, so a failure in any earlier step happens before any image is written.
        """
        covers = self._extras.covers
        for spec in self._bundle.items:
            if self._action(EntityKind.COVER, spec.ref) is None or covers is None:
                continue
            name = self._item_names[spec.ref]
            if (adoption := self._adoption(EntityKind.COVER, spec.ref)) is not None:
                await self._took_back(adoption, spec.ref, name)
                continue
            style = self._extras.cover_styles[spec.type_ref or ""]
            created = await covers.create(self._item_ids[spec.ref], name, style)
            await self._made(EntityKind.COVER, spec.ref, name, created)

    def result(self) -> AppliedBundle:
        """Count what was created and what was left as the person had it."""
        totals = Counter(e.kind for e in self._plan.entities)
        counted = [k for k in EntityKind if k in _ALWAYS_COUNTED or totals[k]]
        created = {kind: self._created[kind] for kind in counted}
        return AppliedBundle(
            bundle_id=self._plan.bundle_id,
            created=created,
            skipped={kind: totals[kind] - created[kind] for kind in counted},
        )
