# Generated Covers for Example Packs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give example items with a natural cover (records, films, board games, recipes) a generated PNG cover at install time, removed with the pack.

**Architecture:** Pack format v3 lets an item type declare a cover style. The examples module gains a `CoverRenderer` port (Pillow adapter) and a `CoverTarget` port bridged to the media use cases in `entrypoints/api/shared`. Covers are recorded as their own entity kind, settled first on removal, and re-adopted with kept items.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy, Pillow, pytest; Playwright for e2e.

**Spec:** `docs/superpowers/specs/2026-10-09-example-pack-covers-design.md`

## Global Constraints

- British English. Fictional content only (no real titles, people, companies).
- Backend: `mypy --strict` incl. tests, ruff, coverage floors (domain/application/shared_kernel 100%, adapters 80%). The examples module must not import graph, media, presets or collections (architecture tests); bridges live in `backend/src/app/entrypoints/api/shared/`.
- In-memory repositories alias stored objects; in-memory UoW does not roll back (spy on writes, assert `uow.committed`).
- Pack format versions 1 and 2 keep loading; the parser stays strict.
- Covers are PNG (never SVG), each under 20 KB, deterministic from the item name, one visible character.
- Never `git add`/`commit`/`push`; the owner commits (one `git add -A`).

## Review Focus

- A reinstall must give byte-identical covers for the same names (deterministic), and a name starting with a non-ASCII or emoji character must still render.
- A cover the person replaced must never be deleted by pack removal, and its item must be kept.
- A failed install part-way must remove the covers it had already attached.
- Removing a pack whose items have covers must not leave orphaned media files or assets behind.
- Covers must not appear in user-facing pack counts or kept-reason text.

---

### Task 1: Pack format v3 and the cover entity kind

**Files:**
- Modify: `backend/src/app/modules/examples/domain/pack.py` (`PackItemType.cover: PackCover | None`, `PackCover(style)`, closed `COVER_STYLES`), the pack parser in `backend/src/app/modules/examples/adapters/` (find it via `grep -rn "menagerist-example-pack"`; accept version 1, 2 and 3; `cover` allowed on any version but documented as v3)
- Modify: `backend/src/app/modules/examples/domain/installation.py` (`EntityKind.COVER`, first in `REMOVAL_ORDER`)
- Test: the existing pack and installation test modules under `backend/tests/modules/examples/`

**Interfaces:**
- Produces: `COVER_STYLES = ("sleeve", "poster", "box", "card")`; `PackCover(style: str)`; `PackItemType.cover`; `EntityKind.COVER = "cover"`.

- [ ] **Step 1:** failing tests: cover parsed and exposed; unknown style, non-object `cover`, extra keys in `cover` are parse errors; versions 1 and 2 without covers unchanged; `REMOVAL_ORDER` starts with `COVER`; every existing pack still parses.
- [ ] **Step 2:** implement; check the Postgres installation repository stores `kind` as text or an enum type (add a migration only if an enum constraint requires it; the examples tables use string kinds, confirm).
- [ ] **Step 3:** `uv run poe lint-backend`, `typecheck-backend`, targeted `pytest backend/tests/modules/examples`.

### Task 2: Cover renderer

**Files:**
- Create: `backend/src/app/modules/examples/ports/cover_renderer.py` (`CoverRenderer` Protocol: `def render(self, name: str, style: str) -> bytes`)
- Create: `backend/src/app/modules/examples/adapters/covers/pillow_cover_renderer.py` and an in-memory/fake sibling `in_memory_cover_renderer.py` (returns a fixed tiny valid PNG, deterministic per input)
- Test: `backend/tests/modules/examples/adapters/test_pillow_cover_renderer.py`

**Interfaces:**
- Produces: `PillowCoverRenderer().render(name, style) -> bytes` (PNG). Sizes: sleeve 512x512, poster 400x600, box 600x450, card 600x400. Background from a hash of the folded name over a fixed palette of 12 colours with sufficient contrast for a white letter; a simple shape per style (sleeve: centred circle "record"; poster: top band; box: inset frame; card: bottom stripe); first character of the name, upper-cased, drawn large with `ImageFont.load_default(size=...)`. Unknown style raises `ValueError`.

- [ ] **Step 1:** failing tests: same input -> identical bytes; different names -> different bytes; valid PNG with the expected size per style (`PIL.Image.open`); under 20 KB for every style; names starting with "É", "ß", a CJK character and an emoji render without error and fall back to "?" when the font has no glyph; empty/whitespace name renders "?"; unknown style raises.
- [ ] **Step 2:** implement (palette contrast checked in a test: luminance contrast with white at least 3:1).
- [ ] **Step 3:** gates as Task 1.

### Task 3: Install, remove and re-adopt covers

**Files:**
- Modify: `backend/src/app/modules/examples/ports/pack_targets.py` (`CoverTarget` Protocol)
- Modify: `backend/src/app/modules/examples/application/install_example_pack.py` (`_install_covers` step after items; adoption), `application/removal.py` (inspect/remove for `EntityKind.COVER`), `domain/installation.py` (`adoptable_records` already generic; confirm covers flow through), the composition root/dependencies that build the install and uninstall use cases
- Modify: `backend/src/app/entrypoints/api/shared/example_targets.py` (`CoverPackTarget` bridge to the media use cases: upload-and-attach as the item's cover, inspect, remove; in-memory variants for tests)
- Test: new `backend/tests/modules/examples/application/test_example_pack_covers.py`; Postgres integration test beside `test_example_install_postgres.py`

**Interfaces:**
- Consumes: Task 1 kinds and `PackItemType.cover`; Task 2 `CoverRenderer`.
- Produces: `CoverTarget.create(item_id: uuid.UUID, name: str, style: str) -> Created` (content `{"style","name","sha256"}`), `CoverTarget.inspect(entity_id) -> Inspection | None` (same content shape from what is stored now; `None` if the cover is gone), `CoverTarget.remove(entity_id) -> RemoveResult`. `InstallResult` and the API response counts are unchanged (covers are not counted).

- [ ] **Step 1:** failing tests (in-memory targets): covers created only for items whose type declares a style; recorded as `COVER` owned; uninstall removes them before the items and the items are removed; a replaced cover (inspect hash differs) is kept and its item is kept with reason `has your connections, files or collections`; a deleted cover settles as removed/already gone and does not block item removal; a failure after some covers were attached rolls them back (spy on target removals); a reinstall after a kept (replaced) cover re-adopts it with the original hash and does not create a second cover; an adopted item whose cover was removed gets a fresh cover; counts and kept-reason text never mention covers.
- [ ] **Step 2:** implement the use-case steps and the bridge. The bridge reuses the media application use cases (upload-and-attach, set-cover, detach/delete) through their existing public constructors; check how `entrypoints/api/shared` already wires other module use cases and follow it. Detaching must delete the asset and its thumbnails so no orphans remain.
- [ ] **Step 3:** Postgres integration test with real media storage on a temp dir: install a pack with covers, assert N attachments/assets exist; uninstall; assert zero assets and zero stored files remain.
- [ ] **Step 4:** `uv run poe lint-backend`, `typecheck-backend`, `uv run poe coverage` (full).

### Task 4: Pack content, docs and end-to-end

**Files:**
- Modify: `backend/src/app/modules/examples/packs/{music,movies,games,recipes}.json` (add `"cover": {"style": ...}` to the record, film, board game and recipe item types; bump `"version"` to 3 where covers are used), `docs/DECISIONS.md`, `backend/README.md` (Example packs section: v3 format and `cover`), `frontend/tests/e2e/examples.spec.ts`
- Test: e2e plus the existing pack-content tests

- [ ] **Step 1:** content edits; the existing content tests (every pack installs and uninstalls cleanly, counts) must still pass.
- [ ] **Step 2:** e2e (chromium; reuse helpers in `frontend/tests/e2e/helpers.ts`): install Movies, a film item shows a cover image (its `<img>` loads, natural width above zero) and a person item shows none; remove Movies, items and covers are gone and the media API lists none for the removed items; install Games, replace one game's cover through the UI/API, remove Games, that game and its cover remain, reinstall re-adopts without a duplicate and the cover is still the replaced one.
- [ ] **Step 3:** docs: a dated 2026-10-09 DECISIONS entry (generated covers, PNG not SVG, covers as a removable entity settled first, replaced covers are the person's file); backend README pack-format paragraph.
- [ ] **Step 4:** full gate: `uv run poe lint`, `uv run poe typecheck`, `uv run poe coverage`, `uv run poe test-frontend`, full `uv run poe test-e2e`; read totals from final summary lines. Hand the owner one commit message.
