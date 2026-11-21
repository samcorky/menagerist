# CSV re-import by key, and connecting rows by name: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A CSV import can recognise rows it imported before by a key column (#556), and can connect each row's item to another item found or created by name (#555).

**Architecture:** The CSV import starts using the keyed path that `plan_bundle` already has (`BundleSource`, source links, `linked`/`matched`), with a transfer unit of work for the link store. For #555, `build_item_bundle` adds one find-or-create bundle item for each distinct name and a plain bundle connection for each row. The planner resolves each of these items by a case-insensitive name lookup, so there is still one plan for the preview and apply.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy (async), pytest; SvelteKit 5 (runes), vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-11-21-csv-reimport-and-connect-by-name-design.md`

**Stack:** two `gh stack` layers. Layer 1 is Tasks 1–5 (#556) on branch `csv-reimport-by-key`. Layer 2 is Tasks 6–10 (#555) on branch `csv-connect-by-name`. Each layer's backend, frontend and e2e tests pass on their own.

## Global Constraints

- British English in copy, comments and docs. Collector-facing words only in the UI (design §24): "connection", "item", never node or edge.
- The source name is `csv:{item_type}:{key_field}`.
- Keys are trimmed, and case counts. Names are trimmed and compared ignoring case. Both are normalised to NFC with runs of whitespace collapsed to one space.
- A connection's link key is `"\x1f".join([row_key, column, folded_name])`, where `folded_name` is the normalised name in lower case, as written in the file.
- `MAX_CONNECTION_COLUMNS = 5`. `Bundle.connection_limit` for a CSV is `MAX_IMPORT_ROWS * MAX_CONNECTION_COLUMNS` (25,000). At most `MAX_IMPORT_ROWS` (5,000) items may be *created* by one import, counting created other items.
- CSV imports have no ledger and no undo. Source links are the only record.
- `restore` travels in both the plan request and the apply request.
- Reasons, verbatim:
  - `"Already imported from {source}."` (existing)
  - `"You deleted this after importing it."`
  - `"No key."`
  - `"You already have this connection."`
  - `"Repeats a connection earlier in this file."`
  - `"More than one of your {type} items is called '{name}'."`
  - `"Not found, and this column does not create items."`
  - `"Left out: an item it joins is not being imported."`
- No milestone on PRs, no attribution lines in commits or PR bodies, and the issue type is set via GraphQL for any new issue.
- Backend: strict mypy, 100% application and domain coverage (`poe coverage`). Frontend: `poe typecheck-frontend`.

## Review Focus

1. **A numeric key column** (an `ID` kept as a number detail) still recognises its rows on re-import. The link key is the cell's text, not the converted number. Pinned in Task 3: `test_a_number_key_column_recognises_rows_again`.
2. **A partly failed apply.** Items are created one transaction at a time, but links are committed once at the end. If an apply fails part-way, the next run must still not duplicate the items it made; it finds them by the key field's value. Pinned in Task 3: `test_items_made_without_links_are_found_by_their_key_next_time`.
3. **The other item type has a required field.** A bare item with only a name would be refused part-way through applying, so the plan must block it first. Pinned in Task 8: `test_creating_a_bare_item_of_a_type_with_required_fields_blocks`.
4. **The same name in different case or spacing across rows** (`eBay`, `eBay `, `ebay`) is one item, created once. Pinned in Task 8: `test_names_differing_in_case_and_spaces_make_one_item`.
5. **A row whose own item is skipped** (ambiguous, no key, or deleted) must not get connections, and its named item must not be created only for its sake. Pinned in Task 7: `test_a_named_item_only_a_skipped_row_names_is_not_created`.

## Rulings made while planning (deviations from the spec's "shape of the work")

- **Named ends are find-or-create bundle items, not a second kind of connection end.** `BundleItem` gains `lookup: NameLookup | None`. The planner resolves such an item by name within its type. If it finds one item it uses that item, if it finds several the item is ambiguous, and if it finds none it is created (or, with `SKIP`, left out). Connections keep plain refs, so the applier, the ambiguous-end rule and the counts all work unchanged. The behaviour is the spec's; only the representation differs.
- **Links are committed once, after apply**, through a new `TransferUnitOfWork`. The graph targets commit each item on its own, so the spec's "inside one unit of work" cannot hold literally. Review Focus 2 covers the gap.
- **The "No key." rule is switched on by `BundleSource.require_keys: bool = False`**, so other bundle sources keep "an item without a key is created".
- **The cap on created items is a plan blocker**, not `Bundle.item_limit`. Validation runs before planning, so it cannot know which named items will be found rather than created. The CSV bundle's `item_limit` becomes `MAX_IMPORT_ROWS * (1 + MAX_CONNECTION_COLUMNS)`.

---

# Layer 1: #556 re-import by key

### Task 1: The pipeline handles deleted items, `restore`, "No key." and what a recognised row matched

**Files:**
- Modify: `backend/src/app/modules/transfer/domain/plan.py` (`PlannedEntity`)
- Modify: `backend/src/app/modules/transfer/domain/bundle.py` (`BundleSource`)
- Modify: `backend/src/app/modules/transfer/application/extras.py` (`BundleExtras`)
- Modify: `backend/src/app/modules/transfer/application/pipeline.py` (`_Planner.items`, `_keyed_item`, `_add`)
- Test: `backend/tests/modules/transfer/application/test_pipeline_source_links.py`

**Interfaces:**
- Produces:
  - `PlannedEntity.matched_id: uuid.UUID | None = None`, `PlannedEntity.matched_name: str | None = None` and `PlannedEntity.changed: tuple[str, ...] = ()`. `changed` holds the field-hash keys (`"name"`, `"description"`, `"tags"`, `"attributes.<key>"`), sorted.
  - `BundleSource.require_keys: bool = False`.
  - `BundleExtras.restore: frozenset[str] = frozenset()`, a set of source keys.

- [ ] **Step 1: Write the failing tests** (replace `test_a_stale_link_plans_create` and `test_a_stale_link_is_repointed_not_duplicated`, since a gone item no longer comes back by default):

```python
async def test_an_item_deleted_after_import_is_not_created_again(shared): ...
    # import film "1", delete it through t.graph.remove, plan again
    # entity.action is UNCHANGED, entity.reason == "You deleted this after importing it."
    # applying creates nothing
async def test_a_restored_key_creates_the_item_and_repoints_its_link(shared): ...
    # extras=BundleExtras(links=..., owner_id=..., restore=frozenset({"1"}))
    # action CREATE; after apply exactly one link for "1", pointing at the new id
async def test_a_recognised_row_names_the_item_it_matched(shared): ...
    # entity.matched_id == first import's id, entity.matched_name == "Alien"
async def test_a_recognised_row_lists_the_fields_changed_in_the_file(shared): ...
    # second import with year=1980 instead of 1979: entity.changed == ("attributes.year",)
    # and the node's year is still 1979
async def test_a_hand_made_match_names_the_item_too(shared): ...
    # matched_id set, changed == ()
async def test_a_row_without_a_key_is_ambiguous_when_keys_are_required(shared): ...
    # BundleSource(name="lddb", key_field="upc", require_keys=True), item source_key=None
    # action AMBIGUOUS, reason "No key."; nothing created
```

Keep `test_a_row_without_a_key_value_is_created` as it is: without `require_keys`, the behaviour is unchanged.

- [ ] **Step 2: Run them and see them fail**

Run: `poe test-backend --mode agent tests/modules/transfer/application/test_pipeline_source_links.py`
Expected: FAIL. The new fields don't exist yet, and a gone item plans CREATE.

- [ ] **Step 3: Implement**

`_Planner.items`:
- When `keyed` is set, `spec.source_key is None`, `spec.lookup is None` (the `lookup` field arrives in Task 7; until then, just the `source_key` test) and `keyed.source.require_keys` is true, call `self._ambiguous(ref, name, "No key.")`.

`_keyed_item`:
- **A live link.** Keep the existing "Already imported" skip. Set `matched_id` and `matched_name` from `graph.inspect(...).content["name"]`, and `changed = tuple(sorted(link.changed_fields(item_field_hashes(spec))))`.
- **A link whose item is gone.** If `key in self._extras.restore`, plan CREATE; the applier's `_link` already re-points the link. Otherwise call `self._skip(ref, name, "You deleted this after importing it.")`. Either way, do not fall through to the hand-made lookup.
- **A hand-made match.** Set `matched_id`, and set `matched_name` to the row's name.

Extend `_add` with keyword-only `matched_id`, `matched_name` and `changed`, all defaulting to empty.

- [ ] **Step 4: Run the file and see it pass**

Run: `poe test-backend --mode agent tests/modules/transfer/application`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/app/modules/transfer backend/tests/modules/transfer/application/test_pipeline_source_links.py
git commit -m "feat(transfer): keep deleted imports deleted, say what a recognised row matched"
```

### Task 2: A transfer unit of work for source links

**Files:**
- Create: `backend/src/app/modules/transfer/ports/unit_of_work.py`
- Create: `backend/src/app/modules/transfer/adapters/persistence/unit_of_work.py`
- Modify: `backend/src/app/modules/transfer/adapters/api/dependencies.py`
- Test: `backend/tests/modules/transfer/adapters/test_transfer_unit_of_work.py` (integration: a link added in one unit and committed is read back by a fresh one; one not committed is gone)

**Interfaces:**
- Produces:
  - `TransferRepos(links: SourceLinkRepository)`, a `kw_only` dataclass, and `TransferUnitOfWork = UnitOfWork[TransferRepos]`.
  - `build_transfer_repos(session) -> TransferRepos`, `create_transfer_uow(session_factory) -> TransferUnitOfWork` and `create_in_memory_transfer_uow(repos) -> TransferUnitOfWork`. These mirror `examples/adapters/persistence/unit_of_work.py`.
  - The dependencies `get_transfer_uow` and `get_transfer_repos` (an async generator for reads). They mirror `get_example_uow` and `get_example_repos`.

- [ ] **Step 1:** Write the integration test, using the existing integration DB fixtures that the `source_link_repository` tests use.
- [ ] **Step 2:** `poe test-backend-integration --mode agent tests/modules/transfer/adapters/test_transfer_unit_of_work.py`. Expected: FAIL (import error).
- [ ] **Step 3:** Implement the files above.
- [ ] **Step 4:** Rerun. Expected: PASS. Also run `poe test-backend --mode agent tests/architecture`. Expected: PASS.
- [ ] **Step 5:** Commit: `feat(transfer): add a unit of work for source links`.

### Task 3: The CSV import recognises rows by a key column

**Files:**
- Modify: `backend/src/app/modules/transfer/application/item_import.py`
- Modify: `backend/src/app/modules/transfer/application/csv_rows.py` (add `normalise_text`)
- Modify: `backend/src/app/modules/transfer/adapters/api/dependencies.py` (constructors)
- Test: `backend/tests/modules/transfer/application/test_item_import_reimport.py` (new)
- Modify: `backend/tests/modules/transfer/application/test_item_import.py` and `test_item_import_extra_fields.py` (the `_plan`/`_run` helpers pass the new constructor arguments)

**Interfaces:**
- Consumes: Task 1's fields. From Task 2: `TransferRepos`, `TransferUnitOfWork` and `create_in_memory_transfer_uow`.
- Produces:
  - `ItemImportRequest.key_field: str | None = None` and `ItemImportRequest.restore: tuple[str, ...] = ()`.
  - `build_item_bundle(..., key_field: str | None = None)`. It sets `Bundle.source = BundleSource(name=f"csv:{item_type}:{key_field}", key_field=key_field, require_keys=True)`, and sets each item's `source_key` to the key column's `normalise_text(cell)`, or `None` when that is empty.
  - `normalise_text(text: str) -> str`: NFC, then `" ".join(text.split())`.
  - `PlanItemImport(guard, presets, graph, links: SourceLinkRepository)` and `ImportItems(guard, presets, graph, uow: TransferUnitOfWork)`.

- [ ] **Step 1: Write the failing tests** (an `ALICE` member and the `signature` type, as in `test_item_import.py`; add a `code` text field as the key):

```python
async def test_without_a_key_column_nothing_is_recorded(shared): ...      # two runs -> items twice
async def test_a_second_run_creates_only_new_rows(shared): ...           # rows 1,2 then 1,2,3 -> 3 items
async def test_a_recognised_row_is_unchanged_and_names_its_item(shared): ...
    # entity.reason == "Already imported from csv:signature:code."
async def test_a_kept_detail_can_be_the_key(shared): ...                 # ExtraField key "ref"
async def test_a_number_key_column_recognises_rows_again(shared): ...    # kept as NUMBER
async def test_an_empty_key_cell_skips_the_row(shared): ...              # AMBIGUOUS "No key."
async def test_keys_are_trimmed_and_case_counts(shared): ...             # " A1" == "A1", "a1" new
async def test_a_deleted_row_stays_deleted_unless_restored(shared): ...  # restore=("A1",)
async def test_an_unmapped_key_column_is_refused(shared): ...
    # InvalidImportFileError "Recognise rows by a column you map to a field or keep."
async def test_items_made_without_links_are_found_by_their_key_next_time(shared): ...
    # first run without key_field, second with it: unchanged, "Matches your existing item..."
async def test_links_are_committed_with_the_import(shared): ...          # uow.committed is True
```

- [ ] **Step 2:** `poe test-backend --mode agent tests/modules/transfer/application/test_item_import_reimport.py`. Expected: FAIL.

- [ ] **Step 3: Implement**
  - **The key field.** `key_field` may be `"name"`, a mapped field key, or a kept detail's key. Anything else raises `InvalidImportFileError("Recognise rows by a column you map to a field or keep.")`. The key cell is read from the key column's own index, before conversion.
  - **`_plan`.** It takes the links repository and builds `BundleExtras(links=links, owner_id=actor.id, restore=frozenset(request.restore))`. Pass `actor` into `_plan`.
  - **`ImportItems._handle`.** It opens `async with self._uow as repos:`, plans and applies with one shared extras built on `repos.links`, then calls `await self._uow.commit()`.
- [ ] **Step 4:** `poe test-backend --mode agent tests/modules/transfer`. Expected: PASS.
- [ ] **Step 5:** Commit: `feat(transfer): recognise CSV rows imported before by a key column`.

### Task 4: The API takes the key column and `restore`, and says what each row matched

**Files:**
- Modify: `backend/src/app/modules/transfer/adapters/api/items/router.py`
- Modify: `backend/src/app/modules/transfer/adapters/api/plan_schemas.py`
- Regenerate: `openapi.json` and `frontend/src/lib/api/generated/`
- Test: `backend/tests/modules/transfer/adapters/test_item_import_router.py`

**Interfaces:**
- Produces:
  - **Form fields** on `/imports/items/plan` and `/imports/items`:
    - `key_field: str | None`, described as "The field or kept detail that recognises rows imported before."
    - `restore: Json[list[str]] = []`, described as "Keys of rows deleted after an earlier import to create again."
  - **`PlannedEntityResponse`** gains:
    - `matched_id: uuid.UUID | None`;
    - `matched_name: str | None`;
    - `changed: list[str]`, described as "Fields whose value in the file differs from what was last imported."
    - Update the examples to show a recognised row.

- [ ] **Step 1:** Write the router tests:
  - `test_plan_with_a_key_column_reports_recognised_rows`: post twice through the in-memory app, and check `matched_name` and `changed` on the second plan.
  - `test_restore_is_read_as_json`.
- [ ] **Step 2:** `poe test-backend --mode agent tests/modules/transfer/adapters/test_item_import_router.py`. Expected: FAIL.
- [ ] **Step 3:** Implement. Then run `poe dump-schema`, `poe lint-schema` and `poe generate-frontend-client`.
- [ ] **Step 4:** Rerun the router tests. Expected: PASS. `poe lint-schema`: no findings.
- [ ] **Step 5:** Commit: `feat(api): take a key column and rows to restore on item imports`.

### Task 5: The import page picks the key column and shows the re-import preview

**Files:**
- Modify: `frontend/src/lib/csv-import.ts` (key options, form body)
- Modify: `frontend/src/lib/import-plan.ts` (groups for a re-import)
- Modify: `frontend/src/routes/items/import/+page.svelte`
- Test: `frontend/tests/csv-import.test.ts`, `frontend/tests/import-plan.test.ts`, `frontend/tests/e2e/csv-import.spec.ts`

**Interfaces:**
- Produces:
  - `keyOptions(choices: ColumnChoice[], fields: ItemField[]): { value: string; label: string }[]`. It lists name, the mapped fields and the kept details, in column order.
  - `summarisePlan` returns, beside today's groups:
    - `recognised: { label: string; matched: string; changed: string[] }[]`, where `changed` holds field titles mapped from the hash keys;
    - `deleted: { key: string; label: string }[]`;
    - `skipped: { label: string; reason: string }[]`.

- [ ] **Step 1: Write the failing unit tests**
  - `keyOptions` leaves out ignored, description and tags columns.
  - `keyOptions` follows a renamed kept detail.
  - `summarisePlan` puts `"You deleted this after importing it."` entries in `deleted`.
  - `summarisePlan` maps `attributes.price` to "Price" in `changed`.
- [ ] **Step 2:** `poe test-frontend --mode agent`. Expected: FAIL.
- [ ] **Step 3: Implement**
  - **On the match step**, add a native select "Recognise rows already imported by", with "Nothing (import every row)" first. Send `key_field` and `restore` in `body()`.
  - **On the preview step**, show these sections:
    - New;
    - "Already imported", listing the matched item and "Changed in the file: Price, Notes";
    - "Deleted after importing", with a tick per row and a "Bring them all back" button that re-plans with `restore`;
    - "Skipped", with reasons.
  - Follow DESIGN_GUIDELINES §§1–3, §15 and §24.
- [ ] **Step 4:** Run `poe test-frontend --mode agent` and `poe typecheck-frontend --mode agent`. Expected: PASS.
- [ ] **Step 5: e2e.** Add `test('a re-import keyed by ID adds only new rows and keeps deletions', ...)` to `csv-import.spec.ts`, using the spec's autograph sample:
  1. Import keyed by `ID`.
  2. Import again with one more row, and expect "1 item" new and "Already imported".
  3. Delete one item through the API and re-import, and expect it under "Deleted after importing".
  4. Tick it, import, and expect it back.

  Run: `poe test-e2e --mode agent csv-import`. Expected: PASS.
- [ ] **Step 6:** Commit: `feat(frontend): recognise rows already imported on the CSV import page`. Then `gh stack init`, push, and `gh stack submit` for layer 1. The PR body says "Closes #556", with no milestone and no attribution.

---

# Layer 2: #555 connect by name

### Task 6: Name lookups that ignore case

**Files:**
- Modify: `backend/src/app/modules/graph/ports/node_repository.py`, `adapters/persistence/node_repository.py` and `adapters/persistence/in_memory_node_repository.py` (`ids_with_name`)
- Modify: `backend/src/app/modules/transfer/ports/targets.py` and `backend/src/app/entrypoints/api/shared/bridges/transfer_targets.py` (`find_items_by_field`)
- Test: `backend/tests/modules/graph/adapters/persistence/test_in_memory_node_lookup.py` and `test_node_lookup.py` (integration)

**Interfaces:**
- Produces:
  - `ids_with_name(type_slug, name, *, scope, limit, ignore_case: bool = False)`. With `ignore_case`, it compares `lower(name)` on both sides; SQL uses `func.lower(NodeModel.name) == func.lower(name)`.
  - `GraphTarget.find_items_by_field(type_slug, key, value, *, limit=2, ignore_case: bool = False)`. `ignore_case` applies only when `key == "name"`.

- [ ] **Step 1:** Write the tests:
  - `test_ids_with_name_can_ignore_case`: "Rick Astley" is found by "rick astley" only with `ignore_case=True`.
  - The same test for the SQL repository.
- [ ] **Step 2:** Run `poe test-backend --mode agent tests/modules/graph/adapters/persistence/test_in_memory_node_lookup.py` and the integration file. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Rerun both. Expected: PASS.
- [ ] **Step 5:** Commit: `feat(graph): find items by name ignoring case`. Then run `gh stack add csv-connect-by-name` before this commit.

### Task 7: Find-or-create items, connection links and duplicate checks in the pipeline

**Files:**
- Modify: `backend/src/app/modules/transfer/domain/bundle.py`
- Modify: `backend/src/app/modules/transfer/application/extras.py`
- Modify: `backend/src/app/modules/transfer/application/pipeline.py`
- Test: `backend/tests/modules/transfer/application/test_pipeline_named_items.py` (new); `backend/tests/modules/transfer/domain/test_bundle.py` (validation)

**Interfaces:**
- Consumes: from Task 6, `find_items_by_field(..., ignore_case=True)`. From Task 1, `restore` and `require_keys`.
- Produces:
  - **`NameLookup(StrEnum)`**, with `CREATE = "create"` and `SKIP = "skip"`.
  - **`BundleItem.lookup: NameLookup | None = None`**. The `Bundle` refuses an item that has both `lookup` and `source_key` ("an item found by name has no source key"), and `require_keys` ignores items with `lookup`.
  - **`BundleConnection.source_key: str | None = None`**. It is refused without a bundle `source`, as items' keys are.
  - **`Bundle.connection_limit: int = MAX_CONNECTIONS`**, which replaces `MAX_CONNECTIONS` in `_check_size`.
  - **`BundleExtras.named: dict[str, uuid.UUID]`**, which maps an item ref to the existing item its name found; planning fills it.
  - **`_Planner.connections`** becomes `async def connections(self, graph)`.

- [ ] **Step 1: Write the failing tests**

```python
async def test_a_named_item_that_exists_is_used_not_created(shared): ...
    # existing person "Rick Astley"; lookup item "rick astley" -> UNCHANGED, connection CREATE to it
async def test_two_items_with_the_name_make_it_ambiguous(shared): ...
    # reason "More than one of your person items is called 'Rick Astley'."; connection left out
async def test_a_missing_name_is_created_once(shared): ...
async def test_a_missing_name_with_skip_is_not_created(shared): ...
    # UNCHANGED "Not found, and this column does not create items."; connection left out
async def test_an_existing_connection_is_not_made_again(shared): ...      # "You already have this connection."
async def test_a_repeated_connection_in_the_file_is_made_once(shared): ...
async def test_a_deleted_imported_connection_stays_deleted(shared): ...    # keyed connection, removed edge
async def test_a_restored_connection_key_brings_it_back(shared): ...
async def test_a_recognised_row_still_gets_a_missing_connection(shared): ...
async def test_a_named_item_only_a_skipped_row_names_is_not_created(shared): ...
async def test_a_connection_to_an_item_not_imported_is_left_out(shared): ...
    # "Left out: an item it joins is not being imported."
async def test_the_connection_limit_is_the_bundles(shared): ...           # domain test
```

- [ ] **Step 2:** `poe test-backend --mode agent tests/modules/transfer`. Expected: FAIL.

- [ ] **Step 3: Implement.** The planner's decisions, in order:
  1. **Items.** An item with `lookup` is looked up with `find_items_by_field(slug, "name", name, ignore_case=True)`. One match is planned UNCHANGED and stored in `named` and `_item_ids`. Several matches are planned `_ambiguous`. With no match it is planned CREATE, or UNCHANGED with the skip reason (added to `_not_created`, with no id). Do this after every row item is planned.
  2. **Needed items.** A lookup item is *needed* only if a connection joins it to a row item that is being created or already has an id. A lookup item that is not needed is planned UNCHANGED with `"Left out: an item it joins is not being imported."` and is not looked up.
  3. **Connections**, each in this order:
     1. If an end has no id and is not being created, it is planned UNCHANGED with the left-out reason. This replaces the old ambiguous-key reason, so update `test_a_connection_to_an_ambiguous_item_is_left_out`.
     2. If it has a `source_key` and its link's edge is live, it is UNCHANGED, "Already imported". If the link's edge is gone and the key is not in `restore`, it is UNCHANGED, "You deleted this after importing it."
     3. If the same `(source, target, type)` already appeared in the file, it is UNCHANGED, "Repeats a connection earlier in this file."
     4. If both ends are existing ids and `graph.connection_exists(...)`, it is UNCHANGED, "You already have this connection."
     5. Otherwise it is CREATE.
  4. **The applier** creates only the connections that are planned CREATE, after the adoption check. It treats `named` like `linked` and links each created connection with a source key: kind `CONNECTION`, fields `{}`, and it re-points an existing link.
- [ ] **Step 4:** `poe test-backend --mode agent tests/modules/transfer` and `tests/modules/examples`. Expected: PASS, with the example packs unchanged.
- [ ] **Step 5:** Commit: `feat(transfer): plan items found by name and connections made once`.

### Task 8: The CSV import connects a column's names

**Files:**
- Modify: `backend/src/app/modules/transfer/domain/tabular.py` (`ConnectionColumn`, `ConnectionEnd`, `MAX_CONNECTION_COLUMNS`)
- Modify: `backend/src/app/modules/transfer/application/item_import.py`
- Test: `backend/tests/modules/transfer/application/test_item_import_connections.py` (new)

**Interfaces:**
- Consumes: Task 7's `NameLookup`, `BundleItem.lookup`, `BundleConnection.source_key` and `Bundle.connection_limit`.
- Produces:
  - `ConnectionEnd(StrEnum)`, with `SOURCE = "source"` and `TARGET = "target"`.
  - `ConnectionColumn(column: str, relationship_type: str, item_type: str, row_end: ConnectionEnd, on_missing: NameLookup = NameLookup.CREATE)`, a frozen `kw_only` dataclass.
  - `ItemImportRequest.connections: tuple[ConnectionColumn, ...] = ()`.
  - `build_item_bundle(..., connections: Sequence[ConnectionColumn] = ())`. It emits:
    - one lookup item per distinct `(item_type, folded name)`, with ref `named-{n}`, the first spelling seen, and `lookup=on_missing`;
    - one `BundleConnection` per row and non-empty cell, with `source_key` set when the row has a key;
    - a `BundleItemType` for each other type;
    - a `BundleRelationshipType(ref=slug, slug=slug, label=slug)` for each relationship type.

- [ ] **Step 1: Write the failing tests**
  - `test_a_column_connects_each_row_to_the_named_item`: the row is the source, using `Where` and an `obtained_at` relationship type.
  - `test_the_row_can_be_the_target`
  - `test_names_differing_in_case_and_spaces_make_one_item`
  - `test_an_empty_cell_makes_no_connection`
  - `test_a_column_can_be_the_name_and_a_connection`
  - `test_more_than_five_connection_columns_are_refused`: `"Connect at most 5 columns."`
  - `test_an_unknown_relationship_type_is_refused`: `"You have no relationship type called 'x'."`
  - `test_an_unknown_other_item_type_is_refused`: the existing `_fields` message.
  - `test_creating_a_bare_item_of_a_type_with_required_fields_blocks`: blocker `"Creating person 'Dave Prowse': {schema message}."`
  - `test_more_than_5000_created_items_block`: blocker `"This import would create more than 5000 items."` Patch `MAX_IMPORT_ROWS` small in the test.
  - `test_the_plan_leaves_out_types_and_relationship_types`
  - `test_re_import_adds_only_missing_connections`
- [ ] **Step 2:** `poe test-backend --mode agent tests/modules/transfer/application/test_item_import_connections.py`. Expected: FAIL.
- [ ] **Step 3: Implement**
  - **Validation.** In `_plan`, check each connection column's types first: `_fields(item_type)` and `graph.slug_taken(RELATIONSHIP_TYPE, slug)`.
  - **Per-row checks.** Run `check_item_attributes` only for row items (`ref` starts with `row-`).
  - **After `plan_bundle`:**
    - run `check_item_attributes(type, {})` for lookup items planned CREATE;
    - add the cap blocker;
    - filter `ITEM_TYPE` and `RELATIONSHIP_TYPE` out of the plan `PlanItemImport` returns.
  - **Limits.** Set `item_limit=MAX_IMPORT_ROWS * (1 + MAX_CONNECTION_COLUMNS)` and `connection_limit=MAX_IMPORT_ROWS * MAX_CONNECTION_COLUMNS`.
- [ ] **Step 4:** `poe test-backend --mode agent tests/modules/transfer`. Expected: PASS.
- [ ] **Step 5:** Commit: `feat(transfer): connect each CSV row to an item named in a column`.

### Task 9: The API takes connection columns

**Files:**
- Modify: `backend/src/app/modules/transfer/adapters/api/items/schemas.py` (`ConnectionColumnEntry`, `ItemImportResultResponse.connections_added`)
- Modify: `backend/src/app/modules/transfer/adapters/api/items/router.py`
- Regenerate: `openapi.json` and the frontend client
- Test: `backend/tests/modules/transfer/adapters/test_item_import_router.py`

**Interfaces:**
- Produces:
  - **The `connections` form field:** `Json[list[ConnectionColumnEntry]] = []`. `ConnectionColumnEntry` has `column`, `relationship_type`, `item_type`, `row_end` and `on_missing`, with `to_domain()`.
  - **`ItemImportResultResponse.connections_added: int`.**

- [ ] **Step 1:** Write `test_an_import_with_a_connection_column_reports_connections_added`.
- [ ] **Step 2:** Run it. Expected: FAIL.
- [ ] **Step 3:** Implement. Then run `poe dump-schema`, `poe lint-schema` and `poe generate-frontend-client`.
- [ ] **Step 4:** Rerun. Expected: PASS, and lint-schema is clean.
- [ ] **Step 5:** Commit: `feat(api): take columns to connect on item imports`.

### Task 10: The import page connects a column

**Files:**
- Modify: `frontend/src/lib/csv-import.ts`, `frontend/src/lib/import-plan.ts` and `frontend/src/routes/items/import/+page.svelte`
- Test: `frontend/tests/csv-import.test.ts`, `frontend/tests/import-plan.test.ts` and `frontend/tests/e2e/csv-import.spec.ts`

**Interfaces:**
- Consumes: Task 9's generated `ConnectionColumnEntry`.
- Produces:
  - `connectColumn(choices, column, settings)` and `connectionsJson(choices): string`.
  - `MAX_CONNECTED = 5`.
  - `summarisePlan(...).toCreate: { type: string; names: string[] }[]` and `connections: { made: number; skipped: { label: string; reason: string }[] }`.

- [ ] **Step 1:** Write the unit tests:
  - a connected column sends one entry, with `on_missing: "create"` by default;
  - a sixth connected column is refused;
  - `summarisePlan` groups the items to create by type.
- [ ] **Step 2:** `poe test-frontend --mode agent`. Expected: FAIL.
- [ ] **Step 3: Implement**
  - **On the match step**, each column's choice list gains "Connect to…". It opens these settings:
    - connection type (the person's relationship types);
    - other item type;
    - "This row's item is the… first / second" (wording from the relationship type's labels);
    - "If there is no item with that name: create it / skip".
  - **On the preview step**, add "Items to create" (by type) and "Connections to make", with skipped connections and their reasons.
- [ ] **Step 4:** Run `poe test-frontend --mode agent` and `poe typecheck-frontend --mode agent`. Expected: PASS.
- [ ] **Step 5: e2e.** Add `test('a column connects rows to items by name, once, and deletions stay deleted', ...)`:
  1. Import the autograph sample keyed by `ID`, with `Where` connected to an `event` type.
  2. Expect one `eBay` event, even with `eBay ` in the file.
  3. Delete one connection and re-import: it stays deleted, and the connection of a newly added row is made.

  Run: `poe test-e2e --mode agent csv-import`. Expected: PASS.
- [ ] **Step 6:** Commit: `feat(frontend): connect a CSV column to items by name`.
- [ ] **Step 7: Final gate.** Run `poe coverage --mode agent`, `poe typecheck-backend --mode agent` and `poe check-changed --mode agent`. Expected: PASS. Then `gh stack push` and `gh stack submit`; the layer 2 PR body says "Closes #555".
