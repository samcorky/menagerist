# Example Packs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user load optional example item types, items, connections and presets from shipped packs, explore them, and remove them cleanly (keeping anything they have changed), with a first-run path that follows `DESIGN_GUIDELINES.md` §3.6.

**Architecture:** A new `examples` bounded context owns pack files, installation records, and install and uninstall use cases. It reaches `graph` and `presets` only through ports it owns, implemented in `entrypoints/api/shared/`. Install is an ordered list of steps, each committed on its own, with compensation on failure. A migration first replaces the unique slug index on the type tables with a partial one so soft-deleted types stop reserving slugs.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy and Alembic, pytest (plus pytest-alembic, testcontainers, archunitpython); SvelteKit with Svelte 5 runes, Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-06-example-packs-design.md`. Read it first. Its open questions are resolved (end of that file).

**State of this plan:** Phases 0 to 4 implemented (2026-10-07); Phase 5 and the follow-ups are not scheduled.

**What changed from the plan:** packs live inside the module as package data, not in `shared/`; `shared/` was split into `data/` and `contracts/` and documented; the movies pack gained a film rating; recipe times use the words display; the backend contract test now also checks every value against its type schema; the "writing an example pack" guide is a section of `backend/README.md`, not a new file.

## Global Constraints

- **Never run `git add` or `git commit`.** Every task ends with the working tree left for the user to review and commit (CLAUDE.md, AGENTS.md).
- Every `.svelte` and `.svelte.ts` file is written or edited through the `svelte-file-editor` subagent.
- Backend: `mypy --strict`; no `from __future__ import annotations`; no quoted annotations (use the `TYPE_CHECKING` import pattern the repo already uses, and the `# noqa: TC001` runtime-import marker where the CQRS signature test needs the class at runtime); Google-style docstrings only where they add value; `kw_only=True, eq=False` on entity dataclasses; `uuid7` ids; timestamps set in domain methods via `datetime.now(UTC)`.
- Dependency direction `entrypoints → adapters → application → domain`. **`examples` must import neither `graph` nor `presets`.** There must be no import cycles (an architecture test enforces it).
- **Layer import limits to remember** (from `tests/architecture/test_architecture.py`): domain may import only `dataclasses, typing, types, uuid, datetime, enum, abc, collections, mimetypes, re` externally, so **no `hashlib` or `json` in domain**. Application and ports may not import fastapi, starlette, sqlalchemy, PIL, filetype or aiofiles.
- Every port ships an in-memory sibling file. Commands take a unit of work and commit; queries take repositories.
- **The application owns every constraint.** Database indexes are backstops. Each rule gets a use-case test on the in-memory stores, in addition to any integration test of the index.
- Coverage floors: domain 100%, application 100%, shared_kernel 100%, adapters 80%, platform 70%.
- British English in code, comments and UI copy. **UI never says "pack", "node", "edge" or "graph"**; say "examples", "items", "item types", "relationships".
- Use `poe` tasks only (`poe` lives at `.venv/bin/poe`; put it on `PATH` in a fresh shell). Per-task checks are named in each task. `poe check-changed` only sees staged files, and nothing is ever staged here, so run the individual tasks.
- No new dependencies.
- Regenerate the frontend client with `poe generate-frontend-client` after any API change; the generated directory is gitignored.

## Execution order and parallelism

```
Phase 0 ─────────────────────────────┐   (ships alone)
Phase 1:  1.1 → 1.2 → 1.3 → 1.4 ┐
                          1.10 ──┤→ 1.5 → 1.6 → 1.7 → 1.8 → 1.9 → 1.11 → 1.12
Phase 2:  2.1 can start after 1.3; 2.2 needs 1.7 + 1.8
Phase 3:  3.1 can start after 1.12 (or earlier against a hand-written fixture)
Phase 4:  alongside each phase; finish last
```

Safe to parallelise: 1.4 (presets change) and 1.10 (file catalogue) are independent of the application tasks. 3.1 (pure helpers) needs only the response shapes in Task 1.11. Everything else is sequential.

Rough sizes: Phase 0 small; Phase 1 large (about 12 tasks, the bulk of the work); Phase 2 medium and mostly content authoring; Phase 3 medium; Phase 4 small.

## Review Focus

- **Slug migration (0.2):** the partial index must keep lookups fast, must not let two *live* types share a slug, and the model's `__table_args__` must match the migration exactly (pytest-alembic `test_model_definitions_match_ddl` fails otherwise).
- **Compensation (1.7):** a failure at every step boundary must leave a recorded, removable state.
- **Removal rules (1.2):** the truth table is the contract. A wrong default here deletes user data.
- **Ownership of existing presets (1.4, 1.5):** a preset that already existed must never be recorded as owned, and so must never be removed.
- **Hash rule (1.2):** one place decides what counts as "the content the pack defined".

---

## Phase 0: Slug uniqueness fix (ships alone)

Fixes an existing bug and unblocks reinstall. Independent of everything else. Source of truth stays in the use cases (`CreateNodeType` and `CreateEdgeType` already check `get_by_slug`, which ignores deleted rows); the index only backs them.

### Task 0.1: Prove the bug (tests first)

**Files:**
- Modify `backend/tests/modules/graph/adapters/persistence/test_node_type_repository.py` (integration; module already has `pytestmark = pytest.mark.integration`)
- Create `backend/tests/modules/graph/adapters/persistence/test_edge_type_repository.py` (no integration test file exists for edge types yet; copy the header of the node type one)

Integration tests use the `db_session` fixture from `tests/conftest.py` (a testcontainers Postgres, migrated by Alembic, each test rolled back via savepoints). **Docker must be running.**

- [ ] `test_slug_can_be_reused_after_soft_delete`: add a type, `soft_delete()`, `save`, flush; add a second type with the same slug; flush. Expect no error. Do this for both node types and edge types.
- [ ] `test_live_types_cannot_share_a_slug`: add two live types with one slug; flush. Expect `sqlalchemy.exc.IntegrityError` (the backstop still works).
- [ ] Run `poe test-backend-integration`. Expected now: the first test fails with a unique violation on `ix_node_types_slug` (and the edge equivalent). Keep that output; it is the evidence that the bug is real.

### Task 0.2: Migration and model

**Files:**
- Create `backend/src/app/alembic/versions/<new_rev>_partial_unique_type_slugs.py` (set `down_revision` to the current single head; check with `poe` or `alembic heads`; `test_single_head_revision` guards this)
- Modify `backend/src/app/modules/graph/adapters/persistence/models.py` (`NodeTypeModel` line 20 and `EdgeTypeModel` line 58 use `mapped_column(unique=True, index=True)`)

- [ ] Migration `upgrade`: drop unique indexes `ix_node_types_slug` and `ix_edge_types_slug`; create plain (non-unique) `ix_node_types_slug` and `ix_edge_types_slug` for lookups; create unique partial indexes `uq_node_types_slug_live` and `uq_edge_types_slug_live` on `slug` with `postgresql_where=sa.text("deleted_at IS NULL")`.
- [ ] Migration `downgrade`: reverse it. Note in the docstring that downgrading fails if a live and a deleted type now share a slug (the full unique index cannot be rebuilt); `test_up_down_consistency` runs on a clean database, so it still passes.
- [ ] Models: `slug: Mapped[str] = mapped_column(index=True)` and `__table_args__ = (Index("uq_node_types_slug_live", "slug", unique=True, postgresql_where=text("deleted_at IS NULL")),)` (and the edge equivalent). The declared index must match the migration exactly.
- [ ] Run `poe migrate` against the local database, then Task 0.1's tests (all pass now), then `tests/platform/test_migrations.py` (pytest-alembic: `test_model_definitions_match_ddl`, `test_up_down_consistency`, `test_upgrade`, `test_single_head_revision`).

### Task 0.3: Use-case tests (the real guarantee)

**Files:** `backend/tests/modules/graph/application/test_create_node_type.py`, `test_create_edge_type.py`, `test_delete_node_type.py`, `test_delete_edge_type.py`

These use `_make_uow()` over the in-memory repositories. Verified while planning: both `InMemoryNodeTypeRepository.get_by_slug` and `InMemoryEdgeTypeRepository.get_by_slug` already ignore soft-deleted rows, like the SQL ones, so no adapter change is needed.

- [ ] `test_create_node_type_succeeds_after_delete_of_same_slug` and the edge equivalent.
- [ ] `test_create_node_type_still_rejects_live_duplicate` already exists (`test_create_node_type_raises_on_slug_conflict`); confirm an equivalent exists for edge types.
- [ ] Add a Postgres-backed delete-then-recreate case through the real unit of work (integration), so the use case and the index are proven together.
- [ ] Checks: `poe lint-backend`, `poe typecheck-backend`, `poe test-backend`, `poe test-backend-integration`.

**Definition of done (Phase 0):** the bug test went red then green; pytest-alembic passes; use-case tests pass without Postgres; no change to any use case's code.

---

## Phase 1: `examples` backend module

> **The detailed, code-level plan for this phase is `docs/superpowers/plans/2026-10-06-example-packs-phase-1-backend.md`.** It supersedes this section where they differ. Differences found while planning it: targets need no `owned_ids` (uninstall order makes it unnecessary); `InstallFailedError` is a plain `Exception` so the existing catch-all returns 500; entity records carry a `label`; every created entity is persisted immediately; the failure rollback and uninstall share one routine; pack files are parsed by a separate strict `pack_parser`. The task list below is kept as the overview.

Build inside-out: domain, application, in-memory adapters, targets, persistence, API.

### Task 1.1: Module skeleton and architecture rule

**Files:** `backend/src/app/modules/examples/{domain,application,ports}/__init__.py`, `adapters/{api,persistence,platform}/__init__.py` (match the `presets` module's `__init__` style); `backend/tests/architecture/test_architecture.py`

- [ ] Add `test_examples_module_is_independent`: `project_files(SRC_PATH).in_folder("*modules/examples*").should_not().depend_on_files().in_folder("*modules/graph*")` and the same for `*modules/presets*` (use the archunitpython API as the existing tests do; check its docs for the exact "depend on files" form). It passes trivially now and must stay green. Mention in the PR that the same rule is not enforced between `graph` and `presets` today.
- [ ] Add `tests/modules/examples/{domain,application,adapters}` mirroring the source tree.

### Task 1.2: Domain

**Files:** `domain/pack.py`, `domain/installation.py`, `domain/removal.py`, `domain/errors.py`; tests under `backend/tests/modules/examples/domain/`. **Tests first.**

Data shapes (frozen where they are values; all `kw_only=True`):

```python
# pack.py (values)
PackPreset(ref, kind, label, description, definition)
PackRelationshipType(ref, slug, label, reverse_label, description, directional, attributes_schema)
PackItemType(ref, slug, label, description, attributes_schema)
PackItem(ref, type_ref, name, description, attributes, tags, extra_schema)
PackConnection(source_ref, target_ref, type_ref, attributes)
ExamplePack(id, presets, relationship_types, item_types, items, connections)   # entity-like aggregate, validates in __post_init__
PackSummary(id, name, description, counts: PackCounts)                         # from the catalogue

# installation.py
EntityKind = Literal["preset", "relationship_type", "item_type", "item", "connection"]
Outcome    = Literal["owned", "removed", "kept"]
EntityRecord(kind, ref, entity_id, content_hash, outcome, reason)               # reason set when kept
Installation(Identifiable, Timestamped): pack_id, status, entities, installed_at, removed_at
Status     = Literal["installing", "installed", "removed", "failed"]
```

Domain stays free of hashing: `content_hash` is an opaque string it compares, produced in the application layer (Task 1.6).

- [ ] `ExamplePack.__post_init__` rejects: a duplicate ref within a section; an item whose `type_ref` is not a defined item type; a connection endpoint or type that is not defined; section sizes over the limits (constants in the module: 200 presets, 50 types each, 500 items, 2000 connections; tune to taste but test the boundary); an item type slug equal to another's. Raises `InvalidPackError(ValidationError)`.
- [ ] `Installation`: `start(pack_id)` classmethod (status `installing`), `record(kind, ref, entity_id, content_hash)`, `mark_installed()`, `mark_failed()`, `mark_removed()`, `owned()` (records still `owned`), `adopt(record, reason)` and `remove(record)` update outcomes. Illegal transitions raise `InvalidInstallationStateError`. Tests cover every legal and illegal transition.
- [ ] `decide_removal(record, inspection) -> RemovalDecision` as a pure function and a **truth table test**, one row per case:

| record outcome | inspection | decision |
|---|---|---|
| owned | missing or deleted | `already_gone` |
| owned | hash differs | `keep("edited")` |
| owned | hash same, `has_user_data` | `keep("has your connections or files")` |
| owned | hash same, `still_in_use` | `keep("still in use")` |
| owned | hash same, none of the above | `remove` |
| kept or removed | anything | `skip` (never act twice) |

  Precedence when several apply: `edited` before `has your connections or files` before `still in use`. A test pins it.
- [ ] Errors (subclass `shared_kernel.errors` bases so the global handler maps them): `PackNotFoundError(NotFoundError)`, `PackAlreadyInstalledError(ConflictError)`, `PackNotInstalledError(ConflictError)`, `SlugClashError(ConflictError)` (carries the slug and kind), `InvalidPackError(ValidationError)`, `InvalidInstallationStateError(ConflictError)`, `InstallFailedError(DomainError)` (carries the cause message).
- [ ] Checks: `poe lint-backend`, `poe typecheck-backend`, domain coverage 100%.

### Task 1.3: Ports and in-memory adapters

**Files:** `ports/{pack_catalogue,installation_repository,unit_of_work,pack_targets}.py`; `adapters/persistence/in_memory_installation_repository.py`; `adapters/platform/in_memory_pack_catalogue.py`

- [ ] `PackCatalogue(Protocol)`: `async list_packs() -> list[PackSummary]`; `async get(pack_id: str) -> ExamplePack | None`.
- [ ] `InstallationRepository(Protocol)`: `add`, `save`, `get(id)`, `get_active_for_pack(pack_id)` (status `installing` or `installed`), `list_active()`.
- [ ] `unit_of_work.py`: `ExampleRepos(installations)` dataclass and `ExampleUnitOfWork = UnitOfWork[ExampleRepos]`, as `presets/ports/unit_of_work.py` does.
- [ ] `pack_targets.py` (driven ports owned by `examples`; data only, no use cases or ORM objects in signatures):

```python
@dataclass(kw_only=True) class Created:    entity_id: UUID; content: dict[str, Any]
@dataclass(kw_only=True) class Inspection: content: dict[str, Any]; has_user_data: bool; still_in_use: bool
@dataclass(kw_only=True) class PresetOutcome: ref: str; entity_id: UUID; created: bool; content: dict[str, Any]
class RemoveResult(Enum): REMOVED, REFUSED_IN_USE, ALREADY_GONE

class PresetTarget(Protocol):
    async def ensure(self, presets: list[PackPreset]) -> list[PresetOutcome]: ...
    async def inspect(self, preset_id: UUID) -> Inspection | None: ...
    async def remove(self, preset_id: UUID) -> RemoveResult: ...

class GraphTarget(Protocol):
    async def slug_taken(self, kind: Literal["item_type", "relationship_type"], slug: str) -> bool: ...
    async def create_relationship_type(self, spec: PackRelationshipType, presets: Mapping[str, UUID]) -> Created: ...
    async def create_item_type(self, spec: PackItemType, presets: Mapping[str, UUID]) -> Created: ...
    async def create_item(self, spec: PackItem) -> Created: ...
    async def create_connection(self, source: UUID, target: UUID, spec: PackConnection) -> Created: ...
    async def inspect(self, kind: EntityKind, entity_id: UUID) -> Inspection | None: ...
    async def remove(self, kind: EntityKind, entity_id: UUID) -> RemoveResult: ...
```

  `content` is the canonical dict of what the pack defines (the target decides which fields count; items exclude `favourite`), and the application hashes it. That keeps the rule in one place per entity kind and the hash function in the application layer.
- [ ] In-memory `InstallationRepository` and `PackCatalogue` as sibling files.
- [ ] Contract tests for the in-memory repository (round trip, active lookup, ordering).

### Task 1.4: `ImportPresets` returns ids (presets module)

**Files:** `backend/src/app/modules/presets/application/import_presets.py`; `backend/tests/modules/presets/application/test_preset_use_cases.py` (or a new `test_import_presets_result.py`); keep the API response unchanged (`ImportPresetsResult` is mapped in `adapters/api/preset/schemas.py`)

- [ ] Test first: for a pack with one new preset and one that already exists, the result's `items` lists, in pack order, `ImportedPreset(id, created)`: the new id with `created=True` and the **existing** preset's id with `created=False` (`_existing_hashes` currently returns only hashes, so it must also keep the id per hash).
- [ ] Add `items: list[ImportedPreset]` to `ImportPresetsResult`; `created` and `skipped` stay. Confirm the router response model is untouched.
- [ ] Checks: `poe test-backend` (presets), application coverage 100%.

### Task 1.5: Target adapters

**Files:** `backend/src/app/entrypoints/api/shared/example_targets.py`; tests in `backend/tests/entrypoints/api/shared/test_example_targets.py`

- [ ] `PresetPackTarget(preset_uow_factory, preset_repos_factory, usage)` wraps `ImportPresets` (for `ensure`), `GetPreset`/the repository (for `inspect`) and `DeletePreset` (for `remove`; map `PresetInUseError` (an item type still references it) and `BuiltinPresetError` (built-ins cannot be deleted) to `REFUSED_IN_USE`, and `PresetNotFoundError` to `ALREADY_GONE`; these are the errors `delete_preset.py` documents). A built-in preset can never be pack-owned, but the mapping makes a bad pack harmless.
- [ ] `GraphPackTarget(graph_uow_factory, graph_repos_factory, media_repos_factory, choice_lists)` wraps `CreateEdgeType`, `CreateNodeType`, `CreateNode`, `CreateEdge`, `DeleteEdge`, `DeleteNode`, `DeleteNodeType`, `DeleteEdgeType`. `inspect` reads the repositories directly.
- [ ] **Factories, not instances:** each call builds a fresh use case with a fresh unit of work (`create_graph_uow(session_factory)` per call). The `SqlAlchemySessionUnitOfWork` opens a session per `async with`; do not share one across calls.
- [ ] Replace `{"$preset": "<ref>"}` placeholders (spec section 1) in a schema's `x-menagerist.list` with the real preset id (a `presets` ref to id map comes from the `ensure` outcomes) before calling `CreateNodeType` / `CreateEdgeType`; fail with `InvalidPackError` if a placeholder has no match.
- [ ] `create_connection` takes real ids resolved by the application; `CreateEdge` auto-creates unknown edge types, so the installer must have created the relationship type first (a test asserts no auto-created type appears).
- [ ] `inspect` for an item: `content = {name, type, description, attributes, tags, extra_schema}` (no `favourite`); `has_user_data` is true if a live edge touches the item whose id is not among the installation's recorded connection ids (the application passes the owned connection ids in), or any media attachment exists (`list_for_target`); `still_in_use` is always false for items. For a type: `has_user_data` false; `still_in_use` true if a live item or connection of that type exists that is **not** in the set being removed (the application passes the ids it is removing).
- [ ] For `remove`, delete in the order the application requests; `DeleteNodeType` clears `type` on remaining items (so the application must never ask to remove a type that still has kept items, per the rules).
- [ ] Tests over the in-memory graph, presets and media stores (`create_in_memory_graph_uow`, `create_in_memory_preset_uow`, and media's in-memory equivalents): each method; `inspect` shows a changed content after an update; a foreign connection or an attachment flips `has_user_data`; a preset referenced by a type returns `REFUSED_IN_USE`; the placeholder substitution; no auto-created types.
- [ ] `inspect(kind, entity_id)` takes no extra parameters: uninstall settles connections, then items, then types, then presets, so "any live connection touches this item" and "any live item has this type" already mean user data and in-use (see the Phase 1 plan's refinements).

### Task 1.6: Application — hashing and queries

**Files:** `application/content_hash.py`, `application/list_example_packs.py`; tests

- [ ] `content_hash(content: dict) -> str`: SHA-256 of canonical JSON (`sort_keys=True`, `separators=(",", ":")`, `ensure_ascii=False`), same approach as `presets/application/pack.py::content_hash`. Tests: key order does not matter; nested order does not matter for dicts; a changed value changes the hash; stable across runs (pin one known hash).
- [ ] `ListExamplePacks(QueryHandler)` takes the catalogue and the installation repository: returns each pack's `PackSummary` plus its active installation (or `None`) and, for an installed pack, record counts by outcome. Tests with the in-memory adapters: none installed, one installed, one removed (shows as not installed), one `failed`.

### Task 1.7: Application — install

**Files:** `application/install_example_pack.py`; tests `backend/tests/modules/examples/application/test_install_example_pack.py`

`InstallExamplePack(CommandHandler[ExampleUnitOfWork, InstallExamplePackCommand, InstallResult])`, constructed with the unit of work, the catalogue, a `PresetTarget` and a `GraphTarget`. Steps are an ordered list (`_STEPS`), each a small class or function with `install(ctx)` and a way to report what it created, so a later media step is one more entry.

**Tests first**, over the in-memory unit of work and the **real** target adapters on in-memory graph, presets and media stores:

- [ ] Happy path: every section created in order; every entity recorded with a hash; status `installed`; counts in the result; one `INFO` log per installation after the final commit.
- [ ] Unknown pack (404 error); already installed (`PackAlreadyInstalledError`); a `removed` installation does not block a new one.
- [ ] **Pre-flight clash:** a live item type with the pack's slug raises `SlugClashError` naming the slug and **creates nothing** (assert the repositories are unchanged and no installation row exists); same for a relationship type slug.
- [ ] An identical preset already in the database is referenced (its id used in the type schema) but **not** recorded `owned`.
- [ ] **Failure injection at each step boundary** (wrap a target so it raises on the Nth call: during presets, relationship types, item types, items, connections): the installation ends `failed`, everything it recorded is removed, no live entity from the pack remains, and `InstallFailedError` carries the cause. Parametrise over the step so a new step is covered automatically.
- [ ] Re-install after a full removal succeeds (this exercises Phase 0 through the use case, on the in-memory stores).
- [ ] A crash simulated by leaving an `installing` row (no failure handling run): a new `InstallExamplePack` call reports `PackAlreadyInstalledError`, and `UninstallExamplePack` (Task 1.8) cleans it up.

Implementation: validate pack and check not active; pre-flight `slug_taken` for every type; `Installation.start` and commit; run steps, recording and committing after each; on exception run the shared removal routine (the same code path as uninstall, over `owned()` records), `mark_failed`, commit, raise `InstallFailedError`; `mark_installed`, commit.

### Task 1.8: Application — uninstall

**Files:** `application/uninstall_example_pack.py`; tests

**Tests first:**

- [ ] Removes everything untouched, in reverse order (connections, items, types, presets), and marks `removed`; counts in the result.
- [ ] Keeps an item whose name was edited (reason `edited`); keeps one with a user-added connection and one with an attached file; a favourited but otherwise untouched item is **removed** (favourite is not an edit).
- [ ] Keeps an item type that still has the user's own items; the type is removed once those are gone.
- [ ] Keeps a preset another type still uses (`REFUSED_IN_USE`).
- [ ] Skips an entity the user already deleted (`already_gone`, recorded as `removed`).
- [ ] Unknown pack; `PackNotInstalledError` when no active installation.
- [ ] Resumes an installation left in `installing` or `failed` (removes what was recorded).
- [ ] After removal, kept entities are no longer pack-owned: installing the pack again does not touch them and `SlugClashError` explains a kept type's slug clash.
- [ ] The result lists, per kept entity, its kind, a human label if the target can supply one, and the reason. Persist the outcomes on the installation record.

Implementation per spec section 4, using `decide_removal`. Order of operations is fixed; compute the set being removed up front so the targets can answer `still_in_use` correctly.

### Task 1.9: Persistence

**Files:** `adapters/persistence/{models,installation_repository,unit_of_work}.py`; `backend/src/app/alembic/versions/<rev>_create_example_installations.py`; `backend/src/app/alembic/env.py` (import the new models, as it does for the others)

- [ ] `ExampleInstallationModel(IdentifiableMixin, TimestampedMixin, Base)`: `pack_id` (text, indexed), `status` (text), `entities` (JSONB list), `installed_at`, `removed_at`. `__tablename__ = "example_installations"`. A partial unique index on `pack_id` where `status IN ('installing', 'installed')` as a backstop only; `InstallExamplePack` already rejects a second active install, covered by an in-memory test.
- [ ] `SqlAlchemyInstallationRepository`, `build_example_repos(session)`, `create_example_uow(session_factory)`, `create_in_memory_example_uow(repos)` (the same three-function shape as `presets/adapters/persistence/unit_of_work.py`).
- [ ] Migration reversible; model and migration must match for pytest-alembic.
- [ ] Integration tests (`@pytest.mark.integration`): round trip including a JSONB `entities` list; status transitions; the backstop index rejects a second active row; `list_active`.
- [ ] Checks: `poe migrate`, `poe test-backend-integration`, `tests/platform/test_migrations.py`.

### Task 1.10: File catalogue

**Files:** `adapters/platform/file_pack_catalogue.py`; tests `backend/tests/modules/examples/adapters/test_file_pack_catalogue.py`

- [ ] Reads `index.json` and `<id>.json` from the module's packaged `packs/` directory (`importlib.resources.files("app.modules.examples") / "packs"`; tests pass an explicit temp directory).
- [ ] Parses JSON into the domain values (the adapter does the parsing; the domain stays pure). Rejects: wrong `format` or `version` on index or pack; an index entry with no file; a file with an `id` that differs from its name or index entry; unknown top-level sections; non-object JSON; unreadable file (raises `InvalidPackError`, never a bare `KeyError`).
- [ ] Caches parsed packs for the process lifetime (packs ship with the app and do not change at runtime); tests assert a second `get` does not re-read.
- [ ] Section counts for `PackSummary` computed here.

### Task 1.11: API

**Files:** `adapters/api/{router,schemas,dependencies}.py` under `modules/examples/adapters/api/example/` (match `presets/adapters/api/preset/` layout: `router.py`, `schemas.py`, and `dependencies.py` at the `api/` level); `backend/src/app/entrypoints/api/__init__.py` (import and `api_v1_router.include_router(example_router)`); router tests; `backend/tests/entrypoints/api/test_api_schemas.py` picks up new schemas automatically (check it, since it validates OpenAPI examples)

- [ ] `router = APIRouter(prefix="/example", tags=["Examples"], route_class=PermissionAwareRoute)`. Do not wrap it in a factory function (README).
- [ ] Routes, `operation_id`s and statuses:

| Route | operation_id | Success | Errors |
|---|---|---|---|
| `GET /api/v1/example` | `list_example_packs` | 200 `list[ExamplePackResponse]` | none expected |
| `PUT /api/v1/example/{pack_id}/installation` | `install_example_pack` | 200 `InstallResultResponse` | 404 unknown pack, 409 already installed or slug clash, 500-class `InstallFailedError` mapped to a problem response with the cause |
| `DELETE /api/v1/example/{pack_id}/installation` | `uninstall_example_pack` | 200 `UninstallResultResponse` | 404 unknown pack, 409 not installed |

- [ ] Schemas: `ExamplePackResponse(id, name, description, counts: PackCountsResponse, installation: InstallationResponse | None)`; `InstallationResponse(status, installed_at, counts)`; `InstallResultResponse(created: counts)`; `UninstallResultResponse(removed: counts, kept: list[KeptEntityResponse(kind, label, reason)])`. No request bodies, so no request model is needed; if one is ever added it must subclass `RequestModel` (extra fields forbidden). Add `json_schema_extra` examples in the `_PRESET_EXAMPLE` style and check they validate.
- [ ] `InstallFailedError`: decide its HTTP mapping. It is neither a client validation error nor a conflict; map it as a 502/500 problem response through `register_exception_handlers` only if a base type fits, otherwise add a handler beside the existing ones. Keep routers free of `try/except`.
- [ ] `dependencies.py`: build the use cases from `get_session_factory`: the examples unit of work, the file catalogue, and the two targets constructed from `create_graph_uow`, `build_graph_repos`, `create_preset_uow`, `build_preset_repos` and the media equivalents (`build_media_repos` and `create_in_memory_media_uow` exist; see how `presets/adapters/api/dependencies.py` builds `GraphPresetUsage`).
- [ ] Router tests with `app.dependency_overrides` (see `presets` router tests): in-memory unit of work, in-memory catalogue, targets built over in-memory stores. Cover 200, 404, 409 (installed twice, slug clash), the uninstall report with kept reasons, and the OpenAPI operation ids.
- [ ] One end-to-end integration test on Postgres: install a tiny test pack through the real stack, uninstall, install again (this is the test that proves Phase 0 through the whole system).
- [ ] Checks: `poe lint-backend`, `poe typecheck-backend`, `poe test-backend`, `poe test-backend-integration`, then `poe coverage` (the full gate).

### Task 1.12: Regenerate the client

- [ ] `poe generate-frontend-client`. Confirm `listExamplePacks`, `installExamplePack`, `uninstallExamplePack` and their response types are exported from `$lib/api/client` (if the client file re-exports by name, add them there).
- [ ] `poe typecheck-frontend` still passes.

**Definition of done (Phase 1):** `poe coverage` green; the architecture suite green including the new rule; an install/uninstall/reinstall round trip passes on Postgres.

---

## Phase 2: Example content

### Task 2.1: Index and the contract test (before the content)

**Files:** `backend/src/app/modules/examples/packs/index.json`; `backend/tests/modules/examples/application/test_shipped_packs.py`; `frontend/tests/example-packs.test.ts` (every field in every shipped pack must map to a known field kind)

- [ ] Write the contract test first, parametrised over every pack listed in `packs/index.json` (so a new pack is covered automatically). For each pack:
  - the file catalogue loads it (format, version, refs, limits);
  - it installs on in-memory graph and presets stores via the real `InstallExamplePack`;
  - **every item passes `validate_attributes` against its type's schema** (the use cases do this on create, so a bad item fails the install; assert the install succeeds);
  - every connection resolves, and its attributes validate against the relationship type's schema;
  - uninstall leaves **zero live entities** from the pack, and a second install succeeds;
  - a **quality floor:** at least one connection per pack; no empty `description` on the index entry, item types or relationship types; every item type has at least one item; every pack preset is referenced by some schema; no duplicate names within a type; all text is British English by a small word-list check (colour, organise, favourite spellings; keep the list short and obvious).
- [ ] It fails until a pack exists. That is intended.
- [ ] Create `packs/index.json` with an entry per pack (id, name, description) so the catalogue tests have real data.

### Task 2.2: Author the packs

**Files:** `backend/src/app/modules/examples/packs/{music,recipes,parts,movies}.json`

**Authoring method (so the JSON shapes are exact):** build each item type in the real UI (Settings, Item types) using the actual field kinds, then copy the schema from `GET /api/v1/node-type` and `GET /api/v1/edge-type`. Do not hand-write schema JSON. Strip server fields (`id`, timestamps) and add `ref`s. Items and connections are written by hand against those schemas.

**Content rules:** all people, bands, companies, albums and events are **fictional**. Never assert real provenance about a real person (no "signed by" a real name). Prefer fields that show off the product: connections that answer a question ("which recipes use eggs?", "what was signed at this event?"), money, partial dates, durations, tables, checklists. Each pack is small enough to read in a sitting.

Agreed content direction (conversation of 2026-10-06; refine each pack as a readable table with the user before writing JSON):

**Style:** UK flavour (prices in GBP, UK places with invented venue and shop names, British dates and spelling, metric units); all people, bands, companies, films and venues fictional; small and finished (8 to 15 items per pack, every item well filled in, a few fields left blank on purpose so blanks look normal); each pack has at least one "wait, it links to that?" path.

1. **`music` - Music (records, artists, gigs, venues, people)** (collector and gigs attended in ONE pack so the provenance story is connected). Agreed table of 2026-10-06:
   - Item types: `record` (pressing year as partial date, formats multiple choice, running time, condition, price paid, notes), `artist` (started as partial date, website), `gig` (date, rating 1 to 5, ticket stub kept), `venue` (city, website), `person` (friends and band members).
   - Items (17): artists The Velvet Static (1989, shoegaze), Marguerite Odell (1996, folk, solo), Tomcat Alibi (2008, no website, split up around 2015); people Priya Nair and Dan Whitcombe (friends) and Ines Calloway, Rob Pennington, Aisha Rahman (Velvet Static members; Aisha played bass 1991 to 1996); venues The Lamplighter (Sheffield) and Cobbles Social Club (Leeds); gigs The Velvet Static at the Lamplighter (14 Mar 2019, 5, stub kept), Marguerite Odell at the Lamplighter (3 Dec 2016, 4, no friends, no stub), Folk and Fuzz night at Cobbles (11 Nov 2023, 4, stub kept, both artists); records Night Drive (LP, 1991, 42:10, Very Good Plus, £34), Paper Lanterns (7", 1994, 3:48, Mint, price blank, a present), Salt Marsh Sessions (LP, 2016, 38:25, Near Mint, £22), Thirteen Bells by Tomcat Alibi (cassette, 2012, Good, £3, car boot sale, running time blank).
   - Relationship types (7): *by*, *featured*, *at*, *went with* (person to gig), *member of* (person to artist; role and joined/left partial dates), *signed by*, *signed at* (signed by carries a surface from a pack choice list and a "signed on" partial date).
   - Connections (about 24): record by artist (4); gig featured artist (4); gig at venue (3); went with (3: Priya and Dan to the 2019 gig, Priya to Cobbles); member of (3); three signings, each signed by plus signed at: Night Drive by the band at the Lamplighter gig (cover, 14 Mar 2019), Salt Marsh Sessions by Marguerite Odell at her Lamplighter gig (inner sleeve, 3 Dec 2016), Paper Lanterns by Ines Calloway only (a person, to show "signed by" may point at a person or an act) at the Cobbles night (sleeve, 11 Nov 2023).
   - Decided against: modelling members who did not tour or did not sign ("three of four"), a second anniversary edition, Tomcat Alibi's gig and members, a friend who is also a former member.
2. **`movies` - Movies watched** (agreed table of 2026-10-06)
   - Decision: a *viewing* is its own item (film, place, date, rating, who with), like a gig, so re-watches are natural. Item types: `film` (year as partial date, runtime, genres, my rating; ratings Cold Harbour 5, The Night Bus Sessions 4, Quiet Hours 3, Marmalade 4), `person` (director, actors, friends), `place` (cinemas, the sofa, a convention), `viewing` (date, rating, note), `memorabilia` (kind: poster, ticket stub or programme; size; condition; price paid; framed; notes).
   - Items (20): films Cold Harbour (2016, 1 h 47, thriller and drama), The Night Bus Sessions (2019, 1 h 34, comedy), Quiet Hours (2022, 1 h 52, drama), Marmalade (2023, 1 h 25, animation and family); people Maggie Trevelyan (director), Callum Frith (actor, who also directed The Night Bus Sessions), Imogen Park (actor), Hannah Okoye and Gareth Rees (friends); places The Regent Picture House (Huddersfield), Dockside Multiplex (Hull), The sofa (no city), Northern Film and Comic Fair (Leeds); five viewings (Cold Harbour at the Regent, 12 Jan 2024, 4; Cold Harbour on the sofa, 3 Nov 2024, 5, a re-watch; Quiet Hours at Dockside, 20 Apr 2023, 3; Marmalade at Dockside, 28 Oct 2023, 4; The Night Bus Sessions on the sofa, 15 Feb 2025, 4); memorabilia: a signed Cold Harbour poster (A3, Very Good, GBP 12, framed, signed by Imogen Park at the convention) and an unsigned Quiet Hours poster (quad, Good, GBP 4, a charity-shop find) kept as contrast.
   - Connections (28): viewing of film (5); viewing at place (5); film directed by person (4); film stars person (5); friend went to viewing (5: Hannah to the first Cold Harbour viewing, Gareth to Quiet Hours, both to Marmalade, Gareth to The Night Bus Sessions); memorabilia for film (2); poster signed by Imogen Park with a "signed on" date (1); poster signed at the convention (1).
   - Decided against: a signed-at-a-viewing (Q&A) story (the convention instead), a separate "cinema" type (a general place covers the sofa and the convention), reusing the Music pack's friends.
3. **`parts` - Electronic parts** (agreed table of 2026-10-06)
   - Item types: `part` (part number, in stock, reorder at, typical price in GBP, datasheet link, notes), `assembly` (built as partial date, build steps as a checklist, notes), `supplier` (website, email, phone, notes). Relationship types: *used in* (part to assembly) carrying a `quantity`, and *supplied by* (part to supplier) carrying the `price` at that supplier. A quantity on the connection, not a table on the assembly.
   - Items (18): 13 parts (10k resistor, 100 nF ceramic capacitor, 470 uF electrolytic capacitor, LM317 voltage regulator, 1N4007 diode, red LED, 10-turn trimmer potentiometer, banana socket pair, Raspberry Pi Pico 2 W, 100 g reel of 0.8 mm solder, green LED, tactile push button, half-size breadboard; LM317 and the trimmer are low on stock, the 470 uF capacitor is close to its reorder line); 3 assemblies (Bench power supply, May 2024, 5 of 6 steps done; Fuzz pedal, 2023, 3 of 4; Pico reaction game, November 2025, 4 of 5); 2 suppliers (Spark & Solder Ltd in Wakefield, Bench Bits in Bristol; invented websites, emails and phone numbers in the reserved fictional 01632 960xxx range).
   - Connections (33): used in (18: power supply 7, fuzz pedal 5, reaction game 6), supplied by (15, with the LM317 and the solder from both suppliers at different prices).
   - Real generic part names (LM317, 1N4007, Raspberry Pi Pico 2 W) are fine for parts; no real companies, shops or people. The solder is a consumable with stock and suppliers but no "used in" connection, on purpose.
   - Decided against: banana sockets are the first part to drop if the pack feels crowded.
4. **`recipes` - Recipes** (agreed table of 2026-10-06)
   - Item types: `recipe` (servings, prep and cook time as durations, dietary multiple choice, rating, ingredients table of ingredient and quantity with unit, method as an ordered list, notes), `source` (kind choice: handwritten, cookbook, person, website; author; year as partial date), `ingredient` (kept: fridge, cupboard or freezer; notes). Relationship types: *from* (recipe to source), *inspired by* (recipe to recipe), *uses* (recipe to ingredient).
   - Items (11): recipes Cheese and onion pie (serves 6, 30 min prep, 45 cook, vegetarian, rated 5, from Nan's recipe tin), Leek and cheddar scones (8, 15 min, 20 min, vegetarian, 4, from The Hungry Weekend, inspired by the pie), Sunday roast chicken (4, 20 min, 1 h 30, dairy-free, 4, from The Hungry Weekend), Parkin (12, 20 min, 1 h, vegetarian, NO rating as not tried yet, from Auntie Jean); sources Nan's recipe tin (handwritten, no year), The Hungry Weekend (cookbook, Ruth Pemberton, 2014), Auntie Jean (person, no year); key ingredients Mature cheddar, Plain flour, Leeks, Black treacle. Full method steps (5 or 6) on every recipe; metric units; UK flavour.
   - Connections (12): from (4); inspired by (1); uses (7: pie cheddar and flour; scones cheddar, flour and leeks; parkin flour and treacle). The roast chicken uses none of the key ingredients on purpose: not everything has to link.
   - Decided against: a vegan or gluten-free recipe (kept small), Table-only methods for some recipes (every recipe gets full steps).
5. **Koillection-style mixed collection - parked.** Needs collections (#265) to be honest rather than faked; revisit when they exist. Open question still: what the user wants people to see (mixed collection, wishlist or value tracking).

Follow-ups: add-on packs with `requires` (for example gig history on top of a collector base) are recorded above and not part of v1.

- [ ] One pack at a time, in the order above (music, recipes, parts, movies; draft each as a readable table first); run Task 2.1's test after each. Stop and ask the user to read each pack before starting the next (content quality is the point of this phase).
- [ ] Keep each pack to roughly 3 item types, 8 to 15 items, 8 to 20 connections.
- [ ] Add any gaps the content exposes (for example a field kind that cannot express something) to a short "Content findings" note in the final report rather than fixing them in this plan.

**Definition of done (Phase 2):** the contract test is green for all shipped packs; the user has read and approved each pack.

---

## Phase 3: Frontend

All `.svelte` and `.svelte.ts` work goes through the `svelte-file-editor` subagent. Read `frontend/README.md` and `frontend/DESIGN_GUIDELINES.md` before starting (sections 3.6, 11, 14, 20a and the loading rules). Use `resolve()` for internal hrefs; shadcn-svelte components (the `Card`, `Button`, `Item`, `Badge` components the home page already uses, and `ResponsiveDialog` for the confirmation); `delayedLoading` for loading states (no skeleton under 300 ms); toasts via `svelte-sonner`; friendly errors, never raw statuses.

### Task 3.1: Pure helpers with tests (no Svelte)

**Files:** `frontend/src/lib/examples.ts`; `frontend/tests/examples.test.ts`

- [ ] **Tests first:**
  - `describeCounts(counts)` gives "3 item types, 14 items" and omits zero parts; singular and plural ("1 item", "2 items"); returns "" for all zeros.
  - `describeRemoval(report)` gives the removed sentence and, when something was kept, a second sentence naming how many and why, grouped by reason ("2 items were kept because you edited them").
  - `reasonLabel(reason)` maps `edited`, `has your connections or files`, `still in use` to friendly phrases; an unknown reason falls back to a neutral phrase.
  - Banner dismissal: `isExamplesBannerDismissed()` and `dismissExamplesBanner()` read and write `localStorage` inside `try/catch` and behave (not dismissed, no throw) when storage throws or is unavailable; mirrors how the "Show built-in" toggle stores its flag (find it with `grep -rn "localStorage" frontend/src/lib`).
- [ ] Implement. Checks: `poe lint-frontend`, `poe typecheck-frontend`, `poe test-frontend`.

### Task 3.2: Examples settings page

**Files:** `frontend/src/routes/settings/examples/+page.svelte`; `frontend/src/routes/settings/+page.svelte` (add an *Examples* card using the same markup as the existing cards, `Sparkles` icon from `@lucide/svelte`)

- [ ] Page title and `<svelte:head>` "Examples - Menagerist". Heading "Examples", subtitle "Try Menagerist with some ready-made items. Remove them whenever you like."
- [ ] A card per pack from `listExamplePacks`: name, description, `describeCounts`, and one button. Not installed: **Add examples**. Installed: a quiet "Added" label plus a **Remove** button.
- [ ] Install: disable the button and show a spinner label ("Adding..."); on success toast "Examples added" with a **View items** action (`goto(resolve('/items'))`); on a slug clash show a friendly message ("You already have an item type called 'Record'. Rename or remove it, then try again.") built from the problem response's `detail`; on any other failure a friendly message with a retry.
- [ ] Remove: opens `ResponsiveDialog`: "Remove these examples?" with what will be removed (`describeCounts` of the installation) and "Anything you've changed or connected to your own items will be kept." Buttons **Remove** (destructive style) and **Cancel**. Move focus back to the card's button on close (§20a).
- [ ] After removal: toast with `describeRemoval`; if anything was kept, show a short inline note on the card listing what and why, until the next action.
- [ ] Loading honours the 300 ms rule; an error state offers retry; empty list (no packs shipped) shows a neutral message.
- [ ] Keyboard and screen-reader: buttons labelled with the pack name ("Add Vinyl and signed items"); results announced via the toast region.
- [ ] Settings index gets the *Examples* card ("Explore Menagerist with ready-made example items.").

### Task 3.3: First-run link and the installed line on Home

**Files:** `frontend/src/routes/+page.svelte`

- [ ] In the existing empty state (`{:else if !loading && totalItems === 0}`), under the *Add your first item* button, a text link (`<a>` styled as a link, not a `Button`): **Or look around with some examples**, `href={resolve('/settings/examples')}`. The primary button stays the only button (§3.5, §3.6).
- [ ] The Home page must know whether examples are installed: call `listExamplePacks` alongside the existing `Promise.all` in `loadData`, tolerating failure silently (the banner is optional).
- [ ] When any pack has an installation, show a dismissible line at the top of the non-empty Home: "You have example items. Remove them when you're ready." with a link to the examples page and a dismiss control; dismissal stored via Task 3.1's helper.
- [ ] The line must not appear for a user with no examples, and must not push the layout on first paint (render only once the pack list has loaded).

### Task 3.4: Vitest for page logic

- [ ] If any logic beyond Task 3.1's helpers is added in components (for example grouping kept reasons), extract it into `examples.ts` and test it there rather than testing components.

### Task 3.5: E2E

**Files:** `frontend/tests/e2e/examples.spec.ts` (uses `helpers.ts`: `uniqueName`, `createItemType`, `createItem`)

Run against the throwaway database (`poe e2e-db-up`, `poe e2e-migrate`, `npx playwright test tests/e2e/examples.spec.ts` from `frontend/`, then `poe e2e-db-down`). The suite shares one database across workers, so examples installed by one test would leak into others: each test must remove what it installed in a `finally` or `afterEach`, and **specs that need an empty home state must be written to tolerate other data** (assert on the link's presence only when the items list is empty, or run the empty-state test first and gate it on `totalItems === 0`). A cold first run can time out starting the backend (`uv` rebuilds the package); retry once.

- [ ] Install from the examples page: items appear on `/items`; the Home line is shown; dismiss it and reload (stays dismissed).
- [ ] Open an example item, follow a connection to a related example item.
- [ ] Remove: items disappear; the type list no longer shows the example types.
- [ ] Edit an example item's name, remove: the edited item is kept, the toast and card note say why.
- [ ] Add your own connection from an example item to your own item, remove: the example item is kept.
- [ ] Reinstall after removal succeeds (regression test for Phase 0).
- [ ] Slug clash: create your own item type with an example's slug, try to install: a friendly error, nothing created.
- [ ] Empty-state link (when the database has no items): navigates to the examples page.
- [ ] Checks: `poe lint-frontend`, `poe typecheck-frontend`, `poe test-frontend`, then `poe test-e2e` for the whole suite before finishing Phase 3.

**Definition of done (Phase 3):** all frontend checks green; the full e2e suite passes; you have walked through it in a browser at phone width as well as desktop (§4, §23).

---

## Phase 4: Documentation

- [ ] `docs/DECISIONS.md` (style: `## Title`, then **Decision**, **Rationale**, optionally **Consequence** or **Not decided**): entries for (0) the intent to extract a generic bundle layer for import and export later (Phase 5), and why it is not built now (no second consumer yet, so the merge policy and export refs would be guesses); (1) the `examples` module and why not the presets pack format or a `source_pack` column; (2) install as per-module commits with compensation, not a cross-module transaction; (3) edit detection by content hash, with the keep rules; (4) the partial slug index and "the application owns every constraint"; (5) pack files as package data inside the `examples` module (not `shared/`, which is for data both sides read); (6) install as an ordered list of steps (media later); (7) the first-run link and why no wizard.
- [ ] `docs/ARCHITECTURE.md`: add `examples/` to the module list and the structure block.
- [ ] `backend/README.md`: a short paragraph in the cross-module section pointing at the target-port pattern (`entrypoints/api/shared/example_targets.py` beside `preset_usage.py`).
- [ ] `frontend/README.md`: note the examples settings page and `lib/examples.ts` if it lists pages and helpers.
- [ ] "Writing an example pack" (format, `ref`s, `$preset`, the authoring method from Task 2.2, the contract test). **AGENTS.md says not to create documentation files unless asked.** Ask the user whether this should be a new `docs/example-packs.md` or a section of `backend/README.md`, and do that.
- [ ] `docs/field-types-spec/PROGRESS.md`: only if field-type docs are touched; otherwise leave it.
- [ ] Mark this plan and the spec's status lines as implemented, with a short "what changed from the plan" note, once it is.

## Phase 5 (not scheduled): reusable bundles for import and export

Raised during Phase 1: user-facing import and export of items, types and (later) collections should use the same code as example packs, not a parallel implementation. This phase is a placeholder with intent and open questions. It needs its own brainstorm and spec before any work starts.

**What Phase 1 already provides (reusable as is)**
- The bundle itself: presets, relationship types, item types, items and connections linked by local refs, with strict parsing and self-validation (`ExamplePack`, `pack_parser`).
- Creation through the normal graph and presets use cases (the target adapters), so imported data gets the same validation as anything typed in by hand.
- Provenance: the installation record with content hashes, which supports "undo this import" and "remove what I have not touched".

**What would be new**
- **Export:** the reverse direction. Read entities and generate stable refs, turn saved-list ids back into `$preset` markers, and decide how media binaries travel (examples are text only).
- **A merge policy for import into existing data:** examples refuse on a slug clash; user imports need rename, merge or skip, chosen per import.
- **Ownership and permissions** once RBAC (#225) exists.
- **Collections:** a new bundle section once #265 lands (needs a format version bump).

**Intended shape**
1. Split the module in two: a generic bundle layer (format, parser, domain, target ports and adapters, creation and settle steps) and, on top of it, the examples catalogue and installation tracking. Phase 1's layering already isolates these, so this is an extraction and rename (`examples` to something like `bundles`), not a rewrite.
2. Converge the existing preset pack format (`menagerist-presets`, `presets/application/pack.py`) so it becomes one section of the bundle rather than a third format.
3. Add export use cases, an import use case with a merge policy, API routes and a UI, in that order.

**Open questions for that spec**
- One envelope format for everything, or per-kind packs that can be combined?
- Are refs stable across exports so a re-import can update, or is every import a new copy?
- What does "remove an import" mean for items the user has since edited (reuse the keep rules)?
- Where do attachments live in a bundle (a zip with a manifest?), and how does that interact with the 16 MB-style size limits elsewhere?

Do nothing for this in Phases 0 to 4 except keep names and boundaries generic where it is free to do so. Record the intent as a decision entry in `docs/DECISIONS.md` during Phase 4.

---

## Risks and how the plan handles them

| Risk | Handling |
|---|---|
| Deleting user data on uninstall | Truth-table tests; keep on any doubt; kept entities become user data; confirmation dialog states what is kept |
| Partial install after a crash | Installation row recorded before and during; uninstall resumes `installing` and `failed` states |
| Two clients install at once | Application check plus backstop index; the second gets `PackAlreadyInstalledError` |
| Hash churn from harmless changes | Hash covers only pack-defined content; `favourite` excluded; no timestamps |
| Slug clash with the user's own type | Pre-flight check before anything is created; friendly message; nothing changed |
| Migration breaks downgrade | Documented limitation; `test_up_down_consistency` covers the clean case |
| Example content is dull or wrong | Contract test quality floor; user reviews each pack; fictional data only |
| E2E suite shares one database | Each test cleans up what it installs; empty-state test gated on an empty database |
| Generated client out of date | Regenerate in Task 1.12 and again after any API tweak |

## Verification before finishing

- [ ] Backend: `poe lint-backend`, `poe typecheck-backend`, `poe test-backend`, `poe test-backend-integration`, `poe coverage`.
- [ ] Frontend: `poe lint-frontend`, `poe typecheck-frontend`, `poe test-frontend`.
- [ ] `poe test-e2e` once for the full suite.
- [ ] Walk through it yourself in a browser: the empty-state link, install each pack, open an example item and follow a connection, edit one item, add your own connection to another, remove, confirm both were kept, reinstall.
- [ ] Leave all changes uncommitted for review; draft a commit message per phase (no `Co-Authored-By` trailer, per the user's standing preference).

## Follow-ups (separate specs)

- **Built-in Countries** through a `builtin:countries` choice source resolved from `shared/data/iso-data.json` (no database row; currencies already work this way). The graph module's `ChoiceListSource` port already exists, so a composite source in `entrypoints/api/shared/` can serve both ids and `builtin:` names; `check_list_refs` currently insists on a UUID and needs to accept the `builtin:` form; the frontend list picker needs a built-in entry.
- **Add-on packs with `requires`.** A pack may declare it needs another pack (for example "Gig history" requires "Collector"), refer to that pack's entities, and be offered on the Examples page once its base is installed ("Adds to: Collector"). The dependency runs one way, so the add-on owns its new connections and ownership stays clear. Needs: a `requires` field in the pack format (version bump), cross-pack refs resolved from the required installation's recorded entities, a guard so the base cannot be removed while an add-on is installed (or removing it removes the add-on first), and a UI state for "needs X first". Considered and rejected: fully conditional bridge links that appear whenever two packs are both installed, because their ownership across two installations breaks the keep rules (a link owned by neither pack makes its endpoint items count as user data) and would need cross-installation bookkeeping. v1 instead ships connected material (records, artists and gigs) inside one Music pack.
- **Reusable bundles for import and export** (see Phase 5 above): extract a generic bundle layer from `examples`, add export, a merge policy and a UI.
- **Opinionated built-in presets as a starter pack** (grades, formats, field groups), once examples exist.
- **Example images.** Needs a media step in the installer (one more entry in the ordered step list), a media-asset source, and removal of attachments. Prefer placeholders generated locally at install time over fetching from an external placeholder service: self-hosted instances may be offline and the server should not pull third-party content. If real pictures are wanted, ship a few small CC0 images beside the packs in the module's `packs/` directory.
- **Done (2026-10-08): a `collections` section** in the pack format (version 2), eight collections across the four packs and a new Board games pack.
- **Done (2026-10-07): the "Example" marker.** `GET /api/v1/example/entities` returns the owned item and item type ids; items show an "Example" badge on cards and in the read view, the items list has an All items / Hide examples / Only examples filter, and example item types are badged on Settings > Item types. Not done: a badge in the item type picker (`category-select.svelte`, a row of pills that a badge would crowd at phone width).
- **`graph` and `presets` independence rule** in the architecture tests, mirroring the one added for `examples`.
- **Done (2026-10-08): the collector pack**, built as a Board games pack (`games`) with four collections.
- **`DeleteNodeType` in-use guard.** Deleting an item type that still has items is not blocked; example removal relies on its own keep rules instead. Related: a referenced choice list can be deleted while in use.
- **Item types in the Hide/Only filter.** The filter applies to items only; the Settings item types list shows the badge but has no filter.
- **`poe test-e2e` ignores failures** (`ignore_fail`), so a green exit does not mean the suite passed. Worth reviewing why it is set.
- **Browser walk-through at phone width** of the Examples page, the items filter and the badges (the Phase 3 definition of done asks for it; not yet done by a person).

Candidates for board cards: example images, add-on packs with `requires`, built-in Countries, the reusable import/export bundles, the starter pack for built-in presets, the `DeleteNodeType` guard, and the `test-e2e` exit code.
