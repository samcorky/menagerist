# Add-on Example Packs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an example pack declare `requires` (a list of pack ids) and refer to its required packs' items, types and relationship types as `pack:ref`, with install refused until the requirements are installed and removal of a base pack blocked while an add-on depends on it.

**Architecture:** Pack format v4 adds `requires` and `pack:ref` references, validated within the pack at parse time and across packs when the catalogue loads. The install use case resolves cross-pack references through the required packs' active installation records and creates the add-on's own entities in its own installation. The uninstall use case refuses while an active installation requires the pack. The pack list API gains `requires` and `required_by` so the Examples page can explain disabled buttons.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy, pytest; SvelteKit 5 runes, Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-09-add-on-packs-design.md` (builds on the example packs design, formats v2/v3 and the re-adoption rule in `docs/DECISIONS.md`).

## Global Constraints

- British English. Fictional content only (no real titles, people, companies); check shipped names against real ones.
- Backend: `mypy --strict` incl. tests, ruff, coverage floors (domain/application/shared_kernel 100%, adapters 80%). The examples module must not import graph, media, presets or collections (architecture tests); bridges live in `backend/src/app/entrypoints/api/shared/`.
- In-memory repositories alias stored objects; in-memory UoW does not roll back (spy on writes, assert `uow.committed`).
- Pack formats 1 to 3 keep loading; the parser stays strict (unknown keys rejected).
- UI text: "pack", "item", "collection"; never node, edge, graph or shelf. Touch targets at least 44 px; disabled controls explained in text.
- Every `.svelte` / `.svelte.ts` edit goes through the `svelte:svelte-file-editor` subagent.
- Never `git add`/`commit`/`push`; the owner commits (one `git add -A`).

## Review Focus

- A cross-pack reference whose prefix is not in `requires` must be a parse error, not a runtime surprise.
- A cycle between add-ons, or an add-on requiring itself, must fail catalogue load with a message naming the packs.
- Installing an add-on while a required pack is only half-installed or removed must be refused; a required entity the person deleted or replaced must be named in the refusal, and nothing may have been created by then.
- Removing a base pack must be blocked by an installed add-on, and unblocked once the add-on is removed; a failed add-on install must leave the base pack and its removal untouched.
- Counts, kept-reason text and re-adoption of an add-on's entities must be unchanged for ordinary packs; cross-pack refs must not leak into another pack's counts.

---

### Task 1: Format v4, `requires` and `pack:ref` in the model and parser

**Files:**
- Modify: `backend/src/app/modules/examples/domain/pack.py` (`ExamplePack.requires: tuple[str, ...]`; a `ref` helper that splits `"pack:ref"`; validation that a prefixed ref's pack is in `requires`; unprefixed validation unchanged)
- Modify: `backend/src/app/modules/examples/adapters/platform/pack_parser.py` (versions 1 to 4; `requires` allowed only on version 4)
- Test: `backend/tests/modules/examples/adapters/test_pack_parser.py`, `backend/tests/modules/examples/domain/test_example_pack.py`

**Interfaces:**
- Produces: `ExamplePack.requires`; `split_ref(ref: str) -> tuple[str | None, str]` returning `(pack_id, local_ref)`; `ExamplePack.external_refs() -> frozenset[tuple[EntityKind, str, str]]` (kind, pack id, local ref) for every cross-pack reference the pack makes, used by the catalogue checks and the install resolver. A prefixed ref is valid only in: an item's `type`, a connection's `from`, `to` and `type`, a collection's `items`. Prefixed refs elsewhere (definitions of the pack's own entities, preset refs) are parse errors.

- [ ] **Step 1:** failing tests: `requires` parsed and exposed; `requires` on a version below 4 rejected; duplicates, self id, non-list, non-string entries rejected; a prefixed ref with a prefix not in `requires` rejected naming the ref; prefixed ref in a disallowed place rejected; own-entity refs unchanged; versions 1 to 3 unchanged; `external_refs()` returns the right kinds (item type, relationship type, item) for each position.
- [ ] **Step 2:** implement; keep refs pattern rules (`_REF`) for the local part and give a clear error for malformed prefixes ("pack:ref needs exactly one colon").
- [ ] **Step 3:** `uv run poe format`, `lint-backend`, `typecheck-backend`, `uv run pytest backend/tests/modules/examples -q -m "not integration"`.

### Task 2: Catalogue validation and summary

**Files:**
- Modify: the pack catalogue adapter in `backend/src/app/modules/examples/adapters/platform/` (find it via `grep -rn "PackCatalogue"`; validate once when the catalogue loads), `domain/pack.py` (`PackSummary.requires`)
- Test: the catalogue adapter's tests under `backend/tests/modules/examples/adapters/`

**Interfaces:**
- Produces: catalogue load raises `InvalidPackError` for: an unknown required pack id; a dependency cycle (message names the packs in the cycle); a cross-pack reference to something the named pack's file does not define, or defines as another kind. `PackSummary.requires: tuple[str, ...]`. `PackCatalogue` gains no new method; `get()` and `list_packs()` behave as before.

- [ ] **Step 1:** failing tests with small in-memory pack sets: unknown require, self-require, two-pack cycle, three-pack cycle, dangling ref, ref of the wrong kind, a valid chain (add-on requiring an add-on) loads and lists with `requires`.
- [ ] **Step 2:** implement the checks as a pure function over all parsed packs (easy to unit test) called by the file-based catalogue at load.
- [ ] **Step 3:** gates as Task 1; the existing shipped packs must still load.

### Task 3: Install, uninstall and the cross-pack resolver

**Files:**
- Create: `backend/src/app/modules/examples/application/external_refs.py` (resolver)
- Modify: `application/install_example_pack.py`, `application/uninstall_example_pack.py`, `domain/errors.py` (`RequirementsNotMetError`, `RequiredByInstalledPackError`, both `ConflictError`), the installation repository port only if a new read is needed (`list_active()` already exists)
- Test: new `backend/tests/modules/examples/application/test_add_on_packs.py`

**Interfaces:**
- Consumes: Task 1 `ExamplePack.requires`, `external_refs()`; Task 2 catalogue validation.
- Produces:
  - `resolve_external_refs(pack, active_installations, targets) -> ResolvedRefs` mapping each `(kind, pack_id, local_ref)` to the live entity (id plus, for item types and relationship types, the slug). Uses the required pack's active installation, only entities it still **owns**, and confirms each still exists through the targets' `inspect`. A required pack with no active finished installation raises `RequirementsNotMetError` ("Add *<name>* first"); a missing or replaced entity raises the same error naming it ("*<pack name>* no longer has *<label>*").
  - The install fills the same `_Run` maps (`type_slugs`, `item_ids`, `item_names`, relationship type slugs) for external refs before the steps run, so item creation, connections and collections use them exactly like local refs. External entities are never recorded in the add-on's installation, so they are never removed by it; a failed add-on install rolls back only its own entities.
  - `UninstallExamplePack` raises `RequiredByInstalledPackError` ("Remove *<add-on name>* first", listing every active dependant) before touching anything.

- [ ] **Step 1:** failing tests (in-memory targets): add-on refused without its base; refused while the base is half installed; installs against the base and creates only its own entities; a connection from an add-on item to a base item exists; a collection can mix base and add-on items; multi-require bridge resolves from two packs; base item deleted by the person -> refusal names it and nothing was created; base entity replaced/edited but still present -> allowed; base uninstall blocked while the add-on is installed, with every dependant named; unblocked after the add-on is removed; removing the add-on removes its connections to base items and leaves base entities untouched; an edited add-on connection is kept and the base item is then kept on base removal; a failed add-on install (force a late failure) leaves the base pack and its record intact; re-adoption of an add-on's kept entities still works; counts exclude external refs.
- [ ] **Step 2:** implement; keep `InstallResult`/counts shapes unchanged.
- [ ] **Step 3:** Postgres integration test in `test_example_install_postgres.py`'s style: install a small base pack and add-on from test packs, assert connections span both, block and unblock removal.
- [ ] **Step 4:** `uv run poe lint-backend`, `typecheck-backend`, `uv run poe coverage` (full).

### Task 4: API surface

**Files:**
- Modify: `backend/src/app/modules/examples/adapters/api/example/schemas.py` (pack list item gains `requires: list[str]` and `required_by: list[str]`), `router.py` (409 responses documented on install and uninstall), the list use case so `required_by` is computed from active installations
- Test: `backend/tests/modules/examples/adapters/test_example_router.py`

**Interfaces:**
- Produces: `GET /example` items carry `requires` (pack ids) and `required_by` (ids of installed add-ons that need this pack, empty for most). Install and uninstall return 409 problem responses with the plain-words messages from Task 3.

- [ ] **Step 1:** failing router tests: list shows `requires` for an add-on and `required_by` for its base once installed; install without the base is 409 with the message; uninstall of a base with a dependant is 409 naming it.
- [ ] **Step 2:** implement; regenerate the client (`uv run poe generate-frontend-client`) and run `uv run poe typecheck-frontend`.
- [ ] **Step 3:** gates.

### Task 5: Examples page (svelte-file-editor)

**Files:**
- Modify: `frontend/src/routes/settings/examples/+page.svelte`, `frontend/src/lib/examples.ts` (pure helpers `addOnNote(pack, packs)` and `blockedReason(pack, packs)`), `frontend/tests/examples.test.ts`

**Interfaces:**
- Consumes: Task 4 generated types (`requires`, `required_by` on a pack).
- Produces: an add-on card shows "Needs *<names>*"; its Add button is disabled with a visible reason until every required pack is installed; a pack with dependants has Remove disabled with "Remove *<names>* first"; the reason text is real text (not only a tooltip), buttons stay at least 44 px, `aria-describedby` ties the reason to the button. Install/remove error toasts use the server's message.

- [ ] **Step 1:** unit tests for the helpers (no requires, one, many, partially installed, dependants listed, names resolved from the pack list, unknown id falls back to the id).
- [ ] **Step 2:** the page change, with the Svelte autofixer run on the real file; e2e additions come in Task 6.
- [ ] **Step 3:** `uv run poe format`, `lint-frontend`, `typecheck-frontend`, `test-frontend`, `npm run build` in `frontend`.

### Task 6: Shipped add-ons, docs and end-to-end

**Files:**
- Create: `backend/src/app/modules/examples/packs/games-extras.json` ("Board games extras", requires `games`), `soundtracks.json` ("Soundtracks", requires `music` and `movies`); modify `packs/index.json`
- Modify: `docs/DECISIONS.md`, `backend/README.md` (Example packs: v4, `requires`, `pack:ref`, removal blocking), `frontend/tests/e2e/examples.spec.ts`

- [ ] **Step 1:** content: invented names only; web-check each new title against real games, films, records and companies; `games-extras` adds about 4 games and one expansion, connects some to base publishers (`games:<publisher-ref>`), and one new collection mixing base and extra games; `soundtracks` adds a few connections between base films and base records (and its own relationship type if needed). Every item name starts with an ASCII letter (covers). Existing pack-content tests must still pass; add content tests for the two add-ons.
- [ ] **Step 2:** e2e (chromium, reuse helpers): Add on "Board games extras" is disabled with its reason until Board games is added; add both, an extra game shows a connection to a base publisher; Remove on Board games is disabled with the reason; remove the add-on then the base; the soundtracks bridge needs both Music and Movies and shows the film-to-record connection on a film's page; a failed/blocked action shows the server message.
- [ ] **Step 3:** docs: dated entry in `DECISIONS.md` (add-ons never change base types; `requires` is a list so bridges are ordinary add-ons; removal blocked not cascaded; edited connections kept; Stage 2 optional links outlined).
- [ ] **Step 4:** full gate: `uv run poe lint`, `uv run poe typecheck`, `uv run poe coverage`, `uv run poe test-frontend`, full `uv run poe test-e2e`; read totals from final summary lines. Hand the owner one commit message.
