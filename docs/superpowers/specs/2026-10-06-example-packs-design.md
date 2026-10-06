# Example packs

**Status:** design agreed in conversation on 2026-10-06 (answers to the four open questions are recorded at the end). Written spec not yet formally reviewed.
**Scope:** backend (new `examples` module, two migrations), frontend (settings page, first-run link), shared data (`shared/examples/`), docs.
**Tracks #266** (loadable example collection). Collections are not modelled here: they are becoming first-class entities (#265), not items, and nothing in this design depends on them.

## Problem

People cannot tell what Menagerist is for until they see concrete examples with connections between items. Today a new database is empty, and the only example content is the built-in presets (lists, fields, field groups) seeded by a migration into every database whether wanted or not.

We want a user to be able to load realistic example item types, items and connections, explore them, and later remove them cleanly, without that content mixing permanently into their own data.

## Goals

1. Optional, loadable **example packs**: item types, relationship types, items, connections and the presets they use.
2. **Clean removal**: removing a pack deletes what it created and the user has not changed, and keeps (and reports) anything the user has edited or added to.
3. **Reinstall works** after removal.
4. A first-run path that respects `DESIGN_GUIDELINES.md` §3.6 (no wizard, no modal, one primary action).
5. Keep the hexagonal boundaries: the new module must not import `graph` or `presets`.

## Principle: the application owns every constraint

Database constraints and indexes are a convenience and a backstop, never the only check. Every rule in this design (a slug is unique among live types, one active installation per pack, ownership of presets) is enforced in the domain or application layer, with a use-case test that does not need Postgres. The index is added as well so a race cannot corrupt data.

## Non-goals

- Example images or other media (text-only in v1). The installer is built as an ordered list of steps so a media step can be added later without changing the others (see Follow-ups).
- Collections of any kind (a later `collections` pack section is possible because the format is versioned).
- Moving the opinionated built-in presets (grades, formats, field groups) into packs. That is a separate decision, see "Follow-ups".
- A marker on example items in the items list.
- Pack dependencies (`requires`). Shared presets are handled by ownership rules below, so they are not needed.

## What the repo gave us

| Finding | Consequence |
|---|---|
| Item types, relationship types, items, connections and presets are all soft-deleted (`SoftDeletableMixin`). | Removal is a soft delete through the existing delete use cases. Same convention, same behaviour as the user deleting them. |
| `node_types.slug` and `edge_types.slug` have a **unique index over all rows, including soft-deleted ones**, while `get_by_slug` ignores deleted rows. | Recreating a type with a deleted type's slug passes the app check and then violates the index. No `IntegrityError` handler exists, so this is very likely a 500 today. It also blocks reinstalling any pack. See decision 1. |
| Cross-module work goes through ports owned by the *consuming* module, implemented in `entrypoints/api/shared/` (`choice_list_source.py`, `preset_usage.py`). The README rejects cross-module transactions. | `examples` owns its ports. Adapters in `entrypoints/api/shared/` call the graph and presets use cases. Install is a sequence of per-module commits with compensation, not one transaction. |
| `ImportPresets` skips presets whose content hash already exists, and returns only counts. | The installer needs ids, including for presets that already existed (skipped), because item type schemas must reference them. Small additive change to its result. |
| `CreateNode` and `CreateEdge` auto-create unknown types. `DeleteNodeType` clears `type` on live items of that slug. | The installer creates types explicitly first. Uninstall must remove items before their type. |
| `DeletePreset` is guarded by `PresetUsage` (cannot delete a preset an item type still references). | Gives us the shared-preset rule for free: a preset another pack or the user still uses is kept and reported. |
| Backend layer rules are folder-based. Nothing stops one module importing another. | Add an architecture test that `examples` imports neither `graph` nor `presets`. |
| `shared_data_path()` plus the Dockerfile already carry `shared/` into the runtime image (`MENAGERIST_SHARED_DIR`). | Pack files go in `shared/examples/`. No packaging or Dockerfile change. |
| `DESIGN_GUIDELINES.md` §3.6: no setup wizard, tour or blocking modal at first run; the empty state is the onboarding with one CTA. §14: confirm destructive actions that cannot be undone. | The first-run link is a quiet secondary link under the single CTA. Removal is confirmed in a dialog that states what is removed and what is kept. UI says "examples", never "pack", "node" or "graph". |

## Design

### 1. Pack files

`shared/examples/index.json` is the catalogue. `shared/examples/<id>.json` is one pack. Names and descriptions live only in the index.

```json
{ "format": "menagerist-examples-index", "version": 1,
  "packs": [ { "id": "vinyl", "name": "Vinyl and signed items", "description": "…" } ] }
```

```json
{ "format": "menagerist-example-pack", "version": 1, "id": "vinyl",
  "presets":            [ { "ref": "condition", "kind": "choice_list", "label": "…", "definition": { } } ],
  "relationship_types": [ { "ref": "signed-by", "slug": "signed-by", "label": "Signed by", "reverse_label": "Signed", "directional": true } ],
  "item_types":         [ { "ref": "record", "slug": "record", "label": "Record", "attributes_schema": { } } ],
  "items":              [ { "ref": "kind-of-blue", "type": "record", "name": "…", "attributes": { }, "tags": [] } ],
  "connections":        [ { "from": "kind-of-blue", "to": "miles-davis", "type": "signed-by" } ] }
```

- Items and connections reference each other by local `ref`, never by id.
- A schema refers to a pack preset as `"x-menagerist": { "list": { "$preset": "condition" } }`. The installer substitutes the real id.
- Unknown top-level sections and unknown versions are rejected, so a later `collections` section needs a version bump.
- Limits mirror preset packs: maximum item counts per section and per-definition size.

### 2. The `examples` module

```
modules/examples/
  domain/        ExamplePack (value objects, ref-integrity invariants), Installation, EntityRecord, removal rules, errors
  application/   ListExamplePacks (query), InstallExamplePack, UninstallExamplePack (commands)
  ports/         PackCatalogue, InstallationRepository, unit_of_work (ExampleRepos), PresetTarget, GraphTarget
  adapters/
    api/         router (+ schemas, dependencies)
    persistence/ models, SqlAlchemy + in-memory InstallationRepository, unit_of_work
    platform/    file_pack_catalogue (reads shared/examples), in_memory_pack_catalogue
```

`PresetTarget` and `GraphTarget` are driven ports owned by `examples`. Their concrete adapters live in `entrypoints/api/shared/example_targets.py` and call the real presets and graph use cases, constructed from unit-of-work factories so application tests can run them over the in-memory graph and presets unit of work with no database.

**Installation** (an entity, `Identifiable` and `Timestamped`): `pack_id`, `status` (`installing`, `installed`, `removed`, `failed`), `installed_at`, `removed_at`, and `entities`: a list of `EntityRecord(kind, ref, entity_id, content_hash, outcome)` where `outcome` is `owned`, `removed` or `kept(reason)`. Stored in one table, `example_installations`, with `entities` as JSONB. A removed installation stays as history; a new install creates a new row.

### 3. Install

Order: presets, relationship types, item types, items, connections.

1. Reject if the pack is unknown, or already has an `installed` installation (409).
2. **Pre-flight, before creating anything:** every type slug the pack uses must be free (`GraphTarget.slug_taken`). On a clash, fail with 409 naming the slug and change nothing.
3. Create the installation as `installing` and commit.
4. Run each step through its target. After each step, record the created ids and content hashes on the installation and commit.
5. A preset that already exists (same content hash) is **not owned** by the pack: it is referenced but never recorded as owned, so it is never removed.
6. On any failure, remove what was recorded (best effort, same code path as uninstall), mark `failed`, and raise `InstallFailedError` with the cause.
7. Mark `installed`.

Because each module commits on its own, a crash mid-install leaves an `installing` row with a precise record of what exists. Uninstall can always clean it up. This replaces a cross-module transaction the README rules out.

### 4. Uninstall

Order: connections, items, item types and relationship types, presets (the reverse of install). For each owned entity the target returns the current content hash and whether it holds **user data**. The decision is a pure function in `domain/`:

| Condition | Outcome |
|---|---|
| Already deleted by the user | skipped, recorded as `removed` |
| Content hash differs from install time | `kept("edited")` |
| Item has a connection not created by the pack, or an attached file | `kept("has your connections or files")` |
| Item type or relationship type still used by live items or connections that are not being removed | `kept("still in use")` |
| Preset the delete guard refuses (still referenced) | `kept("still in use")` |
| Otherwise | removed through the normal delete use case |

Kept entities become ordinary user data (they are no longer pack-owned). The installation is marked `removed` and the response lists removed and kept counts with reasons. Hashing covers the content the pack defines (name, type, description, attributes, tags, extra schema for items; the definition for types and presets). `favourite` is deliberately excluded: starring an example is not editing it.

### 5. Soft-delete and slugs (decision 1)

Replace the full unique index on `slug` for `node_types` and `edge_types` with a **partial unique index `WHERE deleted_at IS NULL`**. The use cases already check uniqueness among live types (`get_by_slug` ignores deleted rows), so the index is only the backstop and now agrees with them. A soft-deleted type then stops reserving its slug, which makes reinstall (and a user recreating a deleted type) work, with no restore operation and no change to the use cases. Soft-deleted rows stay as tombstones. This is a migration on core tables, and it fixes the existing bug independently of examples, so it ships first and on its own.

Rejected alternative: add `restore()` to the soft-delete mixin and every repository and reinstall by undeleting. It touches five repositories plus the 100%-covered shared kernel, leaves the slug bug in place for users, and cannot restore entities the user has since edited.

### 6. API

| Method and path | Purpose |
|---|---|
| `GET /api/v1/example` | Catalogue with per-pack counts (from the file) and installation status |
| `PUT /api/v1/example/{pack_id}/installation` | Install (idempotent: 409 if already installed). Returns counts created |
| `DELETE /api/v1/example/{pack_id}/installation` | Uninstall. Returns removed and kept counts with reasons |

Follows the existing conventions: named request and response models, `operation_id` per route, `PermissionAwareRoute`, unknown request fields rejected, OpenAPI examples valid. Errors subclass the shared-kernel bases (404, 409, 400) so no `try/except` in the router. CLI commands are not needed for v1; the use cases stay reachable from one later.

### 7. Frontend

- **Settings → Examples** (`/settings/examples`): one card per pack with its description, counts ("3 item types, 14 items") and one button, *Add examples* or *Remove*. Installing shows a toast with *View items*. Removing opens a confirmation dialog: what will be removed, and that changed items are kept. After removal, a short summary lists anything kept and why.
- **First run:** the empty home state keeps *Add your first item* as the single primary action. Under it, a quiet text link: *Or look around with some examples*, going to `/settings/examples`. No modal, no wizard.
- **While examples are installed:** a dismissible line at the top of Home, *You have example items. Remove them when you're ready.* with a link to the page. Dismissal is stored per browser (`localStorage`), like the existing "Show built-in" toggle.
- Wording: "examples", "item types", "relationships". Never "pack", "node", "edge" or "graph". "Collection" is avoided here because collections are becoming a distinct concept.

### 8. Content

Three packs for v1, matching the board's list, each small enough to read in one sitting: **Vinyl and signed items** (records, artists, signings, a venue; provenance through *Signed by* and *Signed at*), **Recipes** (a recipe with an ingredients table, ingredients as items where useful), **Workshop parts** (components, *Part of* connections, a quantity field). Every pack must show connections earning their keep. The authoring bar is checked by tests (below) and by you reading them.

### 9. Testing

- **Domain** (100%): pack invariants (duplicate refs, dangling refs, limits), removal rules as a truth table, installation state transitions, hashing stability.
- **Application** (100%): install, uninstall, list, over the in-memory unit of work and the *real* target adapters on the in-memory graph and presets stores. Cover pre-flight clash, mid-install failure with compensation, kept-because-edited, kept-because-connection, kept-because-preset-in-use, reinstall after removal, double install (409).
- **Contract test over shipped content:** every pack in `shared/examples/` passes schema and ref validation, installs into the in-memory stores, passes `validate_attributes` for every item, uninstalls to zero live entities, and installs again. Adding a pack automatically adds this coverage.
- **Adapters** (80%): router tests with dependency overrides; file catalogue against a temp directory; integration tests (`@pytest.mark.integration`) for the SQLAlchemy repository, the partial unique index (delete then recreate a slug), and one end-to-end install and uninstall on Postgres.
- **Architecture:** `examples` imports neither `graph` nor `presets`; existing layer rules cover the rest.
- **Frontend:** vitest for the summary and pluralisation helpers and the banner dismissal logic.
- **E2E (Playwright):** empty state link to install to items visible; remove; edit an example item then remove and see it kept; reinstall.

## Decisions and rejected options

- **New `examples` module** over extending the presets pack format (breaks `presets`' independence from `graph`) or a `source_pack` column on core tables (changes core tables for a non-core feature and cannot detect edits).
- **Install as an ordered list of steps** (presets, relationship types, item types, items, connections), each with install, inspect and remove. A later media step is one more entry.
- **Compensation over a cross-module transaction**, per the README.
- **Content hash over `updated_at`** for edit detection: touching an entity without changing it must not block removal.
- **No `requires` between packs:** ownership and the preset delete guard cover the shared-preset case.
- **Pack files in `shared/examples/`** over module package data: the path helper and Dockerfile copy already exist.

## Follow-ups (not in this plan)

- Built-in Countries via a `builtin:countries` choice source from the shared ISO file (no database row; currencies already work this way). Independent of examples.
- Move the opinionated built-in presets (grades, formats, field groups) into a starter pack, once examples exist.
- Example images. Needs a media step and a binary-asset source. Prefer placeholders generated locally at install time (for example a deterministic tile with the item's initials) over a call to an external placeholder service: self-hosted installs may be offline, and the server should not fetch third-party content. If real pictures are wanted later, ship a few small CC0 images in `shared/examples/`.
- A `collections` pack section, once #265 lands.
- An "Example" marker on items.

## Resolved questions

1. **Slugs:** partial unique index, shipped first on its own. The application and domain remain the source of truth for uniqueness; the index is a backstop.
2. **Images:** deferred. Keep the install code extensible (steps). Placeholders, if used, are generated locally rather than fetched.
3. **Keep rule:** keep items the user edited, connected to, or attached a file to. Agreed.
4. **First-run link:** a small text link under the single CTA, worded *Or look around with some examples*, going to Settings, Examples. Not a top-level navigation item.
