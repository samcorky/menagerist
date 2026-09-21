# Backend surface at a glance

> Part of the field-types spec. Read `00-INDEX.md` and `01-context-and-conventions.md` first (skip the second if this is that file).
> **Type:** reference file. Read alongside each backend item.
> "WI-n" refers to `wi-*.md` files listed in `00-INDEX.md`; "open question N" refers to `open-questions.md`.


Verified against the current `graph` module: one use case per file in `application/` (for example `update_node_type.py`), routers in `adapters/api/<node|edge|node_type|edge_type>/router.py` with singular prefixes (`/node-type`, `/edge-type`), UUID path ids, explicit `operation_id`s, `PermissionAwareRoute`, and conditional requests via `ConditionalRequestDep` (ETag / If-Match) on PATCH.

## New use cases

| Use case | Kind | Work item | Notes |
|---|---|---|---|
| `CountNodeTypeAttributeUsage` | query | WI-9, WI-10 | Nodes of the type holding a key; optional value match (option-in-use count). |
| `CountEdgeTypeAttributeUsage` | query | WI-9, WI-10 | Same for edges. |
| `PurgeNodeTypeAttribute` | command | WI-9 | Removes a key from every node of the type, returns the count. |
| `PurgeEdgeTypeAttribute` | command | WI-9 | Same for edges. |
| `ListNodeTypeCustomAttributes` | query | WI-18c | Keys used by nodes of the type that the schema does not define, with counts. |
| `CreatePreset`, `GetPreset`, `ListPresets`, `UpdatePreset`, `DeletePreset`, `ExportPresets`, `ImportPresets` | commands and queries in a **new `presets` module** | WI-19 | Store and serve saved fields, field sets and choice lists; import and export packs. No dependency on `graph`. |
| `ListAttributeValues`, `ListAttributeValueSuggestions` | queries | WI-21 | Distinct values for type-ahead; clusters of repeated values with existing-item matches and a link-or-choice classification. |
| `LinkAttributeValueToNode` | command | WI-21 | Creates the target item if needed and the edges in one transaction, skipping existing edges. |
| `AdoptNodeTypeCustomAttribute` | command | WI-18b, WI-18c | Adds the new field to the item type and moves values from a custom key to it, per node, where they validate, in one transaction; returns moved and skipped counts. |

Supporting changes: new methods on `NodeRepository` and `EdgeRepository` (for example `count_with_attribute(type_slug, key, value=...)`) with SQLAlchemy JSONB implementations and in-memory siblings.

## New endpoints

| Method and path | `operation_id` | Purpose |
|---|---|---|
| `GET /node-type/{node_type_id}/attribute/{key}/usage` (optional `?value=`) | `count_node_type_attribute_usage` | Returns `{count}`. |
| `DELETE /node-type/{node_type_id}/attribute/{key}` | `purge_node_type_attribute` | Returns `{purged}`, so 200 rather than 204. |
| `GET /edge-type/{edge_type_id}/attribute/{key}/usage` | `count_edge_type_attribute_usage` | Same for edge types. |
| `DELETE /edge-type/{edge_type_id}/attribute/{key}` | `purge_edge_type_attribute` | Same for edge types. |
| `GET /node-type/{node_type_id}/custom-attribute` | `list_node_type_custom_attributes` | Returns `[{key, count}]` (WI-18c). |
| `GET /node-type/{node_type_id}/attribute/{key}/values`, `GET /node-type/{node_type_id}/attribute/{key}/suggestions`, `POST /node-type/{node_type_id}/attribute/{key}/link` | `list_attribute_values`, `list_attribute_value_suggestions`, `link_attribute_value_to_node` | Type-ahead, suggestions and linking (WI-21). |
| `POST /node-type/{node_type_id}/attribute/{key}/adopt` | `adopt_node_type_custom_attribute` | Body `{from_key, property, node_ids?}`, returns `{moved, skipped}` (WI-18b/c). |
| `POST /preset`, `GET /preset`, `GET/PATCH/DELETE /preset/{id}`, `GET /preset/export`, `POST /preset/import` | `create_preset`, `list_presets`, `get_preset`, `update_preset`, `delete_preset`, `export_presets`, `import_presets` | Preset CRUD and packs (WI-19). |

Route shapes are a proposal; match the existing conventions if they differ. Adding these changes the OpenAPI document, so the frontend client must be regenerated (`uv run poe generate-frontend-client`, which CI already runs).

## Ports and adapters

Checked against the current `graph` and `media` modules, `shared_kernel`, `entrypoints/api/__init__.py` and `tests/architecture/`.

**One new port, for one item (WI-19).** It mirrors the `media` module's layout.

| Layer | New | Notes |
|---|---|---|
| `ports/` | `PresetRepository` (Protocol), a `PresetRepos` bundle and `PresetUnitOfWork = UnitOfWork[PresetRepos]` | Same pattern as `GraphRepos` and `GraphUnitOfWork`. |
| `adapters/persistence/` | `preset_repository.py` (SQLAlchemy), `in_memory_preset_repository.py`, `models.py` (`PresetModel`), `unit_of_work.py` | Plus an Alembic migration. The in-memory sibling is required for every port. |
| `adapters/api/preset/` | `router.py`, `schemas.py`, dependency providers | Register `preset_router` in `entrypoints/api/__init__.py`, where routers are listed explicitly. |

The architecture tests pick layers by folder pattern (`*domain*`, `*ports*`, and so on), so a module with the same folder names is covered automatically, and it must not import from `graph`.

**New methods on existing ports.** Each needs a SQLAlchemy and an in-memory implementation.

| Port | Method | Item |
|---|---|---|
| `NodeRepository` | `count_with_attribute(type_slug, key, value=None)` | WI-9, WI-10 |
| `NodeRepository` | `list` and `count` gain an optional `attribute_search_exclusions` argument | WI-17 |
| `NodeRepository` | `list_custom_attribute_counts(type_slug, schema_keys)` | WI-18c |
| `NodeRepository` | a way to page nodes that hold a key (for example a `has_attribute` filter on `list`); the purge (WI-9) and adopt (WI-18) both page and `save` through the unit of work, so no `remove_attribute` method is needed | WI-9, WI-18b, WI-18c |
| `NodeRepository` | `attribute_value_counts(type_slug, key, q=None)`, one method serving both type-ahead and clustering | WI-21 |
| `NodeRepository` | `find_by_normalised_names(names)`, or reuse `list(q=...)` and filter in Python to avoid a new method | WI-21 |
| `EdgeRepository` | `count_with_attribute` (edge-type version only); edge purge pages and saves like nodes | WI-9 |

**No change needed.** `NodeTypeRepository` (existing `list`, `get`, `save` are enough), `EdgeTypeRepository` (`CreateEdge` already auto-creates unknown types), the `GraphRepos` bundle, and, for WI-21's duplicate check, `EdgeRepository`: use the existing `list_for_node` and filter by target and type in the application layer instead of adding an `exists` method.

**Pure code, not ports.**
- Schema-meta accessors and the `validate_attributes` changes (application layer; `jsonschema` is already used there and allowed by the architecture tests).
- The portable-subset pattern check (WI-15), only if free-form regex ships.
- The WI-21 value-normalisation helper belongs in `shared_kernel` next to `slug.py`: `unicodedata` is permitted there but not in the domain layer.
- Node invariants for name limits (WI-18a) are plain domain checks.
- Pack serialisation (WI-19c) is ordinary application code: the pack travels as an HTTP body, so there is no file-storage port.

**Deliberately no new port.**
- Authorisation: none for now (decided). `AuthorizationPort` and `AllowAllAuthorizationAdapter` already exist if it is added later, without a new adapter.
- Events and outbox: no event publisher exists in the code today and the outbox relay is parked, so the WI-9 question about purge events is moot until one does.
- Clock, background worker or queue: everything runs on demand.
- Search index: a later index would sit behind the existing `NodeRepository.list`.
- Built-in preset source: only needed if built-ins load from packaged JSON at startup; seeding through a migration needs none (open question 31).
- Media: Image and File fields are not scheduled. WI-19d (overlay, decided) adds a column and API fields, not a port.

Composite commands (adopt, link) reuse the existing `UnitOfWork` and `JoinedUnitOfWork`.

## Existing use cases that change (no new endpoints)

| Change | Where | Work item |
|---|---|---|
| Changed-keys-only validation | `UpdateNode`, `UpdateEdge`, `_validate_attributes.py` (`previous=` argument) | WI-7 |
| Ignore top-level `required` and archived properties when validating | `_validate_attributes.py` | WI-6, WI-8 |
| Extra schema checks on save (portable-subset pattern check, optional `x-menagerist`, layout and `highlights` shape checks), in one shared helper instead of four copies | `CreateNodeType`, `UpdateNodeType`, `CreateEdgeType`, `UpdateEdgeType` (they already call `check_schema`) | WI-13, WI-14, WI-15 |
| Attribute name limits (length, count per node, non-blank trimmed names) as a domain invariant | `Node.__post_init__` / `Node.update` | WI-18a |
| Attribute search: `ListNodes` also loads node types to build per-type exclusions; `NodeRepository.list` and `count` take `attribute_search_exclusions`; `%` and `_` escaped in `q` | `ListNodes`, `node_repository.py`, in-memory repository | WI-17 |
| Structured validation errors: each error carries `path`, `keyword`, the constraint value and a message, so the client can show "Must start with ..." | `InvalidAttributesError` and its problem-details response | WI-15 |

## Deliberately no new endpoint or schema field

- Archive and restore are ordinary edits of the node type's schema through the existing `PATCH /node-type/{id}` (with its ETag protection), because `archived` is just a flag inside `x-menagerist`.
- Rating, display options, layout, `kind`, `required` and text constraints all live inside `attributes_schema`, which stays a free-form object in the request and response models. No request or response model changes.
- Connection details (WI-22) use the existing `POST /edge` and `PATCH /edge/{id}` and the existing edge validation; the only optional backend addition is a `CreateEdges` command for multi-add.
- Highlights (WI-16) need no backend behaviour beyond shape validation in the shared schema-check helper (keys exist and are not archived, no duplicates, at most 3). `NodeResponse` already returns `attributes`, and search (WI-17) reuses the existing `q` parameter.
- No database tables and no migration, apart from: the `preset` table for WI-19 (a new Alembic migration), the optional index in I-6, a possible later search index (WI-17), and, for WI-19d (overlay, decided), a nullable `extra_schema` column on nodes.
