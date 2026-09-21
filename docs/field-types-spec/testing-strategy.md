# Integration testing strategy

> Part of the field-types spec. Read `00-INDEX.md` and `01-context-and-conventions.md` first (skip the second if this is that file).
> **Type:** reference file. Read alongside each work item.
> "WI-n" refers to `wi-*.md` files listed in `00-INDEX.md`; "open question N" refers to `open-questions.md`.


## What exists today (verified in the repo)

- Backend: unit and in-memory router tests need no infrastructure (`poe test-backend`). Tests that need a real adapter carry `@pytest.mark.integration` and run against a Postgres 18 container started by `testcontainers` (`backend/tests/conftest.py`: session-scoped `postgres_container` and `postgres_url`, migrated to head once; a per-test `db_session` that rolls back via a savepoint). `AGENTS.md` says only tests of the real persistence adapter should be marked integration; there is one precedent for a router-level integration test (`tests/modules/system/adapters/api/test_router.py`). Commands: `poe test-backend-integration`, `poe test-backend-all`, `poe coverage`. CI has a dedicated "Backend Integration Tests" job.
- Frontend: Vitest in a `node` environment (`tests/**/*.test.ts`), with `@lucide/svelte` and `bits-ui` mocked. There is no DOM environment, no component-testing library and no browser end-to-end tooling (none of `jsdom`, `happy-dom`, `@testing-library/svelte` or `playwright` is in `package.json`). Three test files only run once the generated API client exists (`uv run poe generate-frontend-client`, which CI runs first).

Keep to the existing convention: mark a backend test `integration` only when Postgres behaviour is what is being verified. Everything else stays a unit or in-memory router test.

## Layer 1: backend integration tests (real Postgres, existing tooling)

Add to `backend/tests/modules/graph/adapters/persistence/` (and one small API-level file following the `system/.../test_router.py` precedent). All use `pytestmark = pytest.mark.integration` and the existing `db_session` fixture.

| ID | Verifies | Cases |
|---|---|---|
| I-1 | JSONB round-trip fidelity of schemas and attributes | A schema with `x-menagerist` (kinds, `display`, `archived`, `layout`, `required`) survives save and load: array order (layout, `allOf`) preserved; object key order is *not* relied on (JSONB reorders it); patterns with backslashes, unicode and emoji (`"\\.jpg$"`) unchanged; numbers such as `5` and `5.0` and `12.5` compare equal after a round trip; nested group arrays keep order. |
| I-2 | Changed-keys-only validation against stored data (WI-7) | Load a node from Postgres, then update with the same attributes plus one edited field. The unchanged-value comparison must treat the stored and sent values as equal (int/float, nested lists, unicode), so a stale-but-untouched invalid value never blocks the save, and an edited invalid value still does. |
| I-3 | Attribute key count and purge (WI-9) | Count nodes (and edges) of one type that contain a key; purge removes only that key, only for that type, leaves other keys and other types untouched, returns the count, and is idempotent. Each purged node's ETag changes, so a client holding a stale copy gets a 412 on its next save (decided). |
| I-4 | Archive keeps data (WI-8) | Save a node with a value, archive the property in the node type, reload: the value is still stored and returned; edit another field; restore the property: the original value is visible again. |
| I-5 | API-level smoke against real Postgres (in-process ASGI client) | Create a node type using the WI-14 shape, create a node, archive a field, update the node. WI-6: missing a `required` field does not block the save. WI-15: a value missing the prefix is rejected with a validation problem that carries the keyword and value; a cleared optional constrained field saves; a schema with an uncompilable `pattern` is rejected on node-type save. If the purge is made an `AuthorisedCommandHandler`, a caller without its permission is forbidden. |
| I-6 | Migrations | No new migration is expected. `tests/platform/test_migrations.py` (pytest-alembic) must still pass. If WI-9 adds a GIN index on `attributes` to speed up the key-count query (decide by measuring on a few thousand nodes), it ships with an Alembic migration and the migration tests cover it. |
| I-7 | Attribute search (WI-17) | Real-Postgres versions of the verified checks: a value inside a group row matches; key names, booleans and nulls do not; numbers match; archived and `search: false` fields are excluded per type (and only for that type); untyped nodes are scanned in full; a literal `%` in the query matches literally; `count` agrees with `list`. |
| I-8 | Custom-field adoption (WI-18c) | Custom-key listing with counts, scoped to one type and excluding schema keys; adopt moves compatible values only, reports skipped ones, leaves other types untouched, and bumps each moved node's ETag; running adopt twice is a no-op. |
| I-9 | Preset persistence (WI-19) | JSONB round trip of `field`, `field_set` and `choice_list` definitions; `builtin` items cannot be changed or deleted; soft delete; version bump on update; import twice creates no duplicates; the migration for the new table passes the pytest-alembic tests. |
| I-10 | Value suggestions (WI-21) | The clustering and existing-item name-match queries, scoped to one item type and ignoring soft-deleted nodes, empty and non-string values; the link transaction is atomic (rolls back if any edge fails) and idempotent (no duplicate edges on a second run). |

## Layer 2: cross-stack contract fixtures (no database, both suites)

The riskiest seam is the frontend emitting a schema the backend then interprets differently (two regex engines, `x-menagerist`, `required`). Test that seam with shared golden files instead of mocking either side.

- Check a set of fixtures into the repo at one location that both suites read (for example `contract/fixtures/`; see the open question). Each fixture holds a schema plus `valid` and `invalid` attribute documents, and for regex cases the `{pattern, value, expected}` conformance list from WI-15.
- First fixture: a realistic all-kinds schema, such as the Vinyl Record example delivered with this spec (`example-node-type-schema.json`). Add fixtures for a legacy-free minimal schema, a rating, a display-only change (must not change validity), archived fields, a constrained text field, and a layout with rows and tabs (WI-13), and a presets pack (WI-19).
- Frontend (vitest): building the schema from `EditorField`s via the descriptors and `itemsToSchema` produces exactly the fixture's schema; the client validator gives the fixture's expected result for every `valid`/`invalid` document.
- Backend (pytest, unit level): `validate_attributes` gives the same expected result for every document; stripping `x-menagerist` never changes a result (the WI-14 principle); regex conformance cases agree with the frontend's results.
- CI fails when either side drifts, without needing a browser or a database.

## Layer 3: frontend integration

**3a. Module chain (node environment, no new tooling).** Chain the real modules instead of testing each in isolation: schema editor conversion (`schemaToItems` / `itemsToSchema`) → attributes editor (`attributesToRows` / `rowsToAttributes`) → `@cfworker/json-schema`. Cover: choice and date clear (WI-1), blank group cells (WI-2), rating round-trip (WI-5), advisory `required` (WI-6), archived keys hidden from layout and from "Additional details" (WI-8), `display` round-trip (WI-11), recursive `normalise` / `orderedKeys` with rows and tabs and no duplicated fields (WI-13), and a JavaScript-invalid pattern degrading to a warning (WI-15).

**3b. Component tests (decided: not part of this change).** Widget behaviour is covered by 3a and the Playwright flows (3c); add component tests when a widget bug shows the need. The notes below are for that later step. Rendering Svelte components needs a DOM. Add `jsdom` or `happy-dom` plus `@testing-library/svelte` as dev dependencies, enabled per test file so existing node-environment tests are unaffected, and keep the existing `lucide` and `bits-ui` mocks. Record the decision in `docs/DECISIONS.md`. Scope it to behaviour that matters: `RatingInput` hover preview, click, click-to-clear and arrow-key navigation; `ChoiceInput` clearing; `GroupInput` add and remove row with blank cells; the shared layout renderer (rows stack, tabs switch); friendly constraint messages under a field. Anything that depends on the real `bits-ui` calendar or on drag gestures belongs in 3c, not here.

Alternative runner for 3b: Vitest's browser mode (with `vitest-browser-svelte`) runs the same component tests in a real browser through Playwright instead of jsdom. That covers real focus, layout and the actual `bits-ui` widgets without mocks, at the cost of slower runs and a browser install. It needs Vitest 4 or newer (the repo is on `^5.0.1`), and it would share the Playwright browser install that 3c already needs. Choose between jsdom with `@testing-library/svelte` and browser mode when the 3b decision is recorded.

**3c. Browser end-to-end (already planned in `ROADMAP.md`).** `ROADMAP.md` lists a Playwright end-to-end suite (create a node, set a type, add a relationship, quick capture, manage types) as part of the bar for the first merge to `main`, so this is planned work rather than new tooling to debate. The field-type flows below extend that suite.

*Decision: Playwright Test in the frontend package, not pytest or Vitest.*
- **Runner and location.** `@playwright/test` (TypeScript), with `frontend/playwright.config.ts` and specs in `frontend/e2e/*.spec.ts`. Keep specs out of `frontend/tests/`: Vitest includes `tests/**/*.test.ts`, and e2e specs use a different runner, so give `e2e/` its own `tsconfig` and lint globals.
- **Why not `pytest-playwright` in `backend/`.** The backend pytest configuration is built for unit and integration runs (`testpaths = ["tests"]`, `--cov=app` in `addopts`). E2E tests placed there would be collected by `poe test-backend` and `poe coverage`, would require browsers for every unit run, and would count towards nothing. They could live in a separate Python package with its own config, but that gains nothing here: database-level checks already belong to Layer 1, and seeding is better done through the typed frontend API client (below).
- **Why not Vitest as the runner.** Vitest is for unit and component tests. Playwright Test provides retries, the trace viewer, UI mode and per-device projects, which WI-13's phone-width run needs.

*Target and wiring.*
- **Stack.** `compose.dev.yaml` builds and runs `postgres`, `migrate`, `backend` and `frontend` (nginx), with the frontend published on port 8080 as the single entry point. Use `http://localhost:8080` as `baseURL`, and wait for readiness (the backend already exposes `/api/health/ready`) before running specs. Do not use Playwright's `webServer` option to build the app; the stack is started separately.
- **Poe task.** Add `test-e2e` in the `quality` group (`npx playwright test`, `cwd = "frontend"`, matching `test-frontend`). Do **not** add it to the `test` sequence: it needs a running stack and a browser install.
- **CI.** A new `e2e` job in `.github/workflows/ci.yml`, separate from the `prek` and `integration` jobs: checkout, Node 22 with the npm cache, `npm --prefix frontend ci`, `npx playwright install --with-deps chromium`, generate the frontend client, start the compose stack and wait for readiness, run `poe test-e2e`, and upload the HTML report and traces as artifacts when it fails. Consider path filters so it runs on frontend and backend changes only.
- **Projects.** `desktop` (Chromium) and `phone` (a mobile device profile). Run the phone project for flows that check responsive behaviour (WI-13 rows stacking).

*Test data.*
- Seed and clean up through the **public API**, using the generated TypeScript client, so a breaking API change fails the e2e build at compile time. No test-only backend endpoints or database back doors.
- Give each test unique names (for example a random suffix) so tests can run in parallel, and clean up through the API.
- CI starts from a fresh Postgres volume. Local runs should use a separate compose project name so they never touch the developer's own data.

*Suggested flows* (roughly five to ten; a smoke suite, not a second unit suite): create a node type with several kinds; create and edit a node; archive and restore a field; set and clear a rating and a date; save a value that violates a prefix and see the message; highlight a rating and see it on the card (WI-16); search for a value that only exists in an attribute (WI-17); and for WI-13, reorder by dragging and by keyboard, with one desktop and one phone-width run (rows must stack).

## Which item needs which integration coverage

| Work item | Backend (Layer 1) | Contract (Layer 2) | Frontend (Layer 3) |
|---|---|---|---|
| WI-1 to WI-3 | | valid/invalid fixtures | 3a; 3b for choice/date/group widgets |
| WI-4 | I-1 | opaque-property fixture | 3a |
| WI-14 | I-1, I-5 | `x-menagerist` fixtures; validity unchanged without it | 3a |
| WI-5 | I-1 | rating fixture | 3a, 3b (hover, click, keys) |
| WI-6 | I-5 | required-not-enforced fixture | 3a |
| WI-7 | I-2 | | |
| WI-8 | I-4 | archived fixture | 3a, 3c |
| WI-9 | I-3, I-5, I-6 | | 3c |
| WI-10 | I-3 (count of in-use option values) | | 3a |
| WI-11 | | display-does-not-change-validity fixture | 3a, 3b |
| WI-12 | | | 3a (order-independence) |
| WI-13 | | layout fixture | 3a, 3b, 3c |
| WI-15 | I-5 | regex conformance list | 3a, 3b |
| WI-16 | | `highlights` fixture | 3a, 3b (`node-summary`), 3c |
| WI-17 | I-7 | | 3a (match context), 3c |
| WI-21 | I-10 | | 3a, 3c (see suggestion, link items) |
| WI-22 | I-11 (only if `CreateEdges` is added) | | 3a, 3c (edit connection details, multi-add) |
| WI-19 | I-9 | pack fixture (export/import round trip) | 3a, 3c (save a field, add it to another type) |
| WI-18 | I-8 (18c) | custom-key round-trip fixture (number, boolean, null, nested) | 3a, 3c (18b promote flow) |

## Acceptance for this section

- `poe test-backend-integration` passes, and the new backend tests are marked `@pytest.mark.integration` so the existing CI job runs them.
- `poe coverage` thresholds still hold with the integration tests included.
- The shared fixtures are consumed by both the vitest and pytest suites, and both fail if a fixture is edited on one side only.
- 3b (component tests) is deferred by decision; 3a is required. 3c extends the Playwright suite that the roadmap already requires.
