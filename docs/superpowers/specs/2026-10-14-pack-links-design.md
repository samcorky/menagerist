# Optional links between example packs

**Status:** implemented (plan: `docs/superpowers/plans/2026-10-14-pack-links.md`).
**Scope:** Stage 2 of `2026-10-09-add-on-packs-design.md`, which only outlined it. This document replaces that outline.
**Builds on:** pack format v4 (`requires`, `pack:ref`), the installation record and removal rules in `docs/DECISIONS.md`, and the external-reference lookup in `application/external_refs.py`.

## Purpose

Two example packs can be installed independently and still belong together: a soundtrack record and the film it scores. An add-on (`requires`) handles that by forcing a third pack, and it blocks removal of its base. Links make the connections appear on their own once both packs are installed, in either order, and never block anything. That is the point of the examples: show why connections matter, with nothing extra to find.

## Decisions (owner, 2026-10-14)

1. A pack may declare **links** to another pack. A link exists only while both packs are installed (for the same person), whichever was installed second.
2. Links are recorded under the **declaring pack's installation** as ordinary connection records. No new table, no migration.
3. Removal is **never blocked** by links. Links go before either pack's entities do.
4. An **edited** link is kept under the existing removal rule, like any connection.
5. The shipped `soundtracks` add-on is **converted**: Music declares its four "Soundtrack of" links to Movies, and the add-on is deleted.
6. The choice between links and `requires` is the pack author's: `requires` for content that cannot exist without the other pack, `links` for connections that are only nice to have.

## Pack format (version 5)

Version 5 is additive; versions 1 to 4 still load. It allows an optional top-level `"links"` list. Each entry is a connection plus the pack it reaches into:

```json
{
  "with": "movies",
  "from": "night-drive",
  "to": "movies:cold-harbour",
  "type": "soundtrack-of"
}
```

- `with` names one other pack: it exists in the catalogue, is not this pack, and is not in this pack's `requires` (use the add-on mechanism for those).
- `from` and `to` are refs. An unprefixed ref is this pack's own item; a ref prefixed `<with>:` is an item of the `with` pack. At least one end must be prefixed (a link between two of this pack's own items is just a connection), and no prefix other than `with` is allowed.
- `type` is a relationship type **this pack defines** (unprefixed). It is created when this pack installs, whether or not the link ever applies, so the type always exists.
- The same keys as a connection are otherwise allowed (for example `description`).
- A pack may be at version 5 without `requires`, and an add-on may also declare `links` (to a pack other than the ones it requires).

## Catalogue checks (load time)

On top of the existing checks: every `with` pack exists; every `<with>:ref` is an item the `with` pack's file defines; the own ref exists in this pack's file; `type` is one of this pack's relationship types. Violations fail when the catalogue loads, so a bad shipped pack is caught in tests. Links do not take part in the cycle check, because they never require anything.

## Records

A link, once applied, is an `EntityKind.CONNECTION` record in the declaring pack's installation with ref `link:<with>:<n>`, where `n` is its index in the pack's `links` list. The prefix tells removal which links point at which pack. Label as for connections ("Night Drive to Cold Harbour"). Everything else about the record (content hash, outcome, reason) is as for any connection.

`Installation.record` only works while a pack is installing, but links are recorded after it is installed. A second method, `record_late`, accepts an `INSTALLING` or `INSTALLED` installation and otherwise behaves the same.

## Applying links

After a pack finishes installing (status `INSTALLED`, persisted), the installer applies links for the installing person only. Other people's installations are never touched.

1. **Its own links.** For each link whose `with` pack has an active, finished installation of the same person, apply it and record it in this pack's installation.
2. **Links pointing at it.** For each other active, finished installation of the same person whose pack declares links with this pack, apply those links and record them in *that* installation.

Applying one link:

- Resolve the own end from the declaring installation's records and the other end from the `with` pack's installation, using the same lookup add-ons use (`resolve_external_refs`, generalised so it can resolve a given set of references against given installations instead of only `pack.requires`).
- **Skip, quietly,** if either end no longer exists (the person deleted it) or is no longer owned by its pack.
- **Skip** if a connection of that type already joins those two items, whoever made it. A link is therefore idempotent: a reinstall, a repeated apply, or a link the person kept earlier never produces a duplicate, and a kept link is simply still there.
- Otherwise create the connection with the graph target, record it, and persist the declaring installation.

A link failure (a target error) is logged and the link skipped. It never fails or rolls back the pack install, because the pack is already installed and links are optional.

The install result gains `linked` (how many links this install created, in either installation), so the page can say so.

## Removal

Removing pack X, for the same person:

1. First settle every link recorded `with` X in *other* active installations (records of kind `connection`, owned, ref starting `link:X:`). Each is removed, or kept under the existing rule if it was edited; the usual `decide_removal` applies. The other pack's installation is saved. This happens before X's own entities are settled, because those links join X's items.
2. Then X is removed as today. Its own links are ordinary owned connections, so they go with the rest of its connections (first in the removal order).

Nothing is refused. A kept link keeps the item it touches under the existing "has your connections" rule, so removing a pack can still leave an item behind when the person edited a link to it.

## API and UI

- The pack list response gains `links_with`: the ids of packs this pack declares links to. It is read from the catalogue; no extra calls.
- The Examples page adds a quiet line to a pack that has links, such as "Also connects to *Movies* when both are added". The wording avoids graph terminology (see `DESIGN_GUIDELINES.md`). The install success message mentions `linked` when it is above zero.
- No new controls, and nothing is disabled. All `.svelte` edits go through the Svelte editor agent.

## Shipped content

- **Music (v5)** declares the relationship type `music-soundtrack-of` ("Soundtrack of" / "Soundtrack") and the four links to Movies that `soundtracks` has today. Slugs keep the pack prefix.
- **Soundtracks** is removed from the catalogue index and from `packs/`. The list is built from the catalogue, so an existing `soundtracks` installation would stop appearing on the Examples page; its connections stay as the person's own data and the record is harmless. Nothing has been released yet (there is no tagged image), so only development databases can hold one, and no migration is written for it.
- Files that mention `soundtracks` and change with it: `packs/index.json`, `packs/soundtracks.json` (deleted), `backend/README.md`, `tests/modules/examples/application/test_shipped_add_ons.py`, `frontend/tests/e2e/examples-add-ons.spec.ts`, `examples-helpers.ts`, `helpers.ts`, `docs/DECISIONS.md` (the add-on entry is amended, not rewritten), and `docs/superpowers/plans/2026-10-09-add-on-packs.md` (historical, left as it is).
- Names stay fictional, as before.

## Testing

- **Parser:** `links` accepted at v5 only; unknown `with`, self `with`, a `with` already in `requires`, no prefixed end, a second prefix, a type that is not the pack's own: all rejected.
- **Catalogue:** dangling `with`, a `pack:ref` the other file does not define, wrong kind.
- **Application, with in-memory targets:** install A then B and B then A both create the links; links appear in the declaring installation whichever order; the other person's installations are untouched; a deleted endpoint skips quietly; an existing connection of that type is not duplicated; a link failure does not fail the install; remove either pack and the links go, in either order of removal; an edited link is kept and keeps its item; reinstall re-satisfies a kept link; removal is never refused; counts include link connections under the declaring pack.
- **Domain:** `record_late` accepts `INSTALLED` and `INSTALLING` and refuses `REMOVED` and `FAILED`.
- **API:** `links_with` in the list; `linked` in the install result.
- **E2E:** install Music then Movies, see the soundtrack connections on a record; remove Movies, see them go and Music still installed; install Movies first and then Music.
- Coverage floors as in `AGENTS.md`.

## Limits and non-goals

- Two installs running at the same instant could both try the same link. The skip-if-exists check makes a duplicate unlikely but does not rule it out. Accepted and noted in `docs/DECISIONS.md`.
- Links never create items or types in the other pack, and never change the other pack's entities (add-on rule 1 still holds).
- No cross-person links. A person's links join only that person's installations.
- No link-only UI of its own, no "links" count on the Examples page beyond the one line and the install message.
