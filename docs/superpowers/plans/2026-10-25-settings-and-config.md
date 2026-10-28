# Settings and configuration: layered settings, startup logging and public config: plan

# Part 1: layered settings (deployment, instance and user)

Status (2026-10-28): Part 2 prerequisite Phase 1 (source tracking, `INSTANCE_SETTINGS`, startup logging) and Phase 2 (route restructure) are implemented, and the scheduler's Phases 0-3 are implemented (its `ScheduleSource` adapter, `SettingsScheduleSource`, still reads a snapshot of the env settings). Part 1 Phase B (markers and discovery) is implemented; Phases C-G (frontend core, settings module, form, wiring, user scope) are a proposal. Written 2026-10-23 from a design discussion with Sam. This document also contains the earlier settings handoff plan (startup logging, route restructure, public config) as Part 2; its old Phase 4 "settings module" is replaced by Part 1. The scheduler plan (`2026-10-25-scheduler.md`) is the first consumer, through its `ScheduleSource` port.

Facts about the repo come from reading `platform/config/*` (`MenageristBaseSettings`: `env_prefix="MENAGERIST_"`, frozen, `validate_default`; `BackupSettings` with full-name `validation_alias`es; the `INSTANCE_SETTINGS` tuple of cached getters), `shared_kernel/access.py` and the frontend field-type registry (`frontend/src/lib/field-types/registry.ts`, `schema-meta.ts`, `schema-types.ts`). Not read in detail: the frontend settings routes, the query builder's use of the registry, and the number of registry call sites. Phase C counts them first.

Working rules (`AGENTS.md`, `CLAUDE.md`): never create, stage or push commits (ask Sam to commit); British English; `.svelte` and `.svelte.ts` files go through `svelte-file-editor`; run only relevant `poe` checks; coverage floors (domain/application/shared_kernel 100%, adapters 80%, platform 70%); every port has an in-memory sibling; the generated API client is never hand-edited; UI text must not say node, edge or graph.

## Decisions (Sam, 2026-10-23)

1. An env var for a tunable setting **locks** it: the UI shows the value read-only with "set by your deployment". Unsetting the variable unlocks it.
2. Settings without an env var are possible: **DB-only groups** are plain frozen Pydantic `BaseModel`s, so nothing can pin them.
3. Pydantic Settings stays as the deployment layer and is not extended to read the database. The settings module is separate.
4. JSON Schema extras are injected through **annotations**, not repeated `json_schema_extra` dicts.
5. The frontend field types are **extracted into a reusable core**; the item-type schema editor becomes a wrapper adding its own features.
6. Tunables are **flat primitives only**: bool, int, float, str, enum, list of str. "Off" for a schedule is the empty string, as `MENAGERIST_BACKUP_SCHEDULE=` already means.

## Layers and precedence

| Layer | Source | Editable | Applies to |
|---|---|---|---|
| Code default | field default | no | everything |
| Instance | DB row, scope `instance` | admins, in the UI | instance-tunable settings |
| User | DB row, scope `user`, per person | that person | user-scoped settings |
| Deployment pin | env, `.env`, secret file | operators | env-backed fields only |

Effective value, highest first: env pin, user row, instance row, code default. Boot-only settings (database URL, secrets, paths, trusted proxies, hashers, the instance `TZ`) have no `Tunable` marker, never enter the DB and keep using `get_*_settings()`. The instance timezone (`TZ`) and a user's display timezone are different settings; do not let either stand in for the other.

## Backend design

### Markers (shared kernel, no framework imports beyond Pydantic)
- `UIMeta(kind=, unit=, display=)`: a frozen dataclass whose `__get_pydantic_json_schema__` merges the non-`None` keys into the property's `x-menagerist` namespace. Only keys the frontend's `PropertyMeta` already knows are accepted (typed arguments, so a typo fails `mypy --strict`).
- `Tunable(scope=Scope.INSTANCE, restart_required=False)`: server-side marker, never written into the schema. Found by the settings module in `model_fields[name].metadata` (tested to work through nested `Annotated` aliases).
- `Public()`: separate marker for fields exposed by public config. It replaces the `public` flag I first put on `Tunable`, because public config also covers boot-only fields (Part 2 Phase 3 wanted one marker). A registration test rejects `Public` or `Tunable` on `SecretStr`, `SecretBytes` or a URL with credentials.
- Reusable aliases carry validation and UI kind together: `CronSchedule = Annotated[str, AfterValidator(check_cron), UIMeta(kind="cron")]`, `Hours = Annotated[int, Field(gt=0), UIMeta(unit="hours")]`.

### Groups
- **Env-backed** groups stay `MenageristBaseSettings` subclasses; add `Tunable` to the fields an admin may change. A field is locked when its source map says env, `.env` or a secret file supplied it (the Phase 1 source tracking; my sandbox shortcut of checking `os.environ` is not enough).
- **DB-only** groups are `BaseModel`s declared in the owning module (for example instance name, registration open).
- Each module declares its groups; a central list (like `INSTANCE_SETTINGS`) registers them. Auto-discovery is a later option.
- Pydantic's JSON Schema is keyed by validation alias; discovery calls `model_json_schema(by_alias=False)` so keys are field names, and builds the stable setting key `group.field` (for example `backup.keep_last`).

### Settings module (`modules/settings`, its own bounded context)
- **Domain:** setting descriptor (key, scope, schema, default, env name, restart flag), value source (`default`, `instance`, `user`, `env`), errors (`SettingLocked`, `UnknownSetting`, `InvalidSettingValue`) subclassing `shared_kernel.errors`.
- **Ports:** `SettingsRepository` (get, list, upsert, delete by scope, owner and key; in-memory sibling), `DeploymentPins` (key to locked value and env name, built from the tracked settings; in-memory sibling), and the application-facing `SettingsReader` (`get(key) -> value`, typed accessor helpers, per-user variant), also with an in-memory sibling. Consumers such as the scheduler's `ScheduleSource` adapter depend on `SettingsReader` only.
- **Application:** `ListSettings` and `GetSetting` queries (repo only, no UoW); `UpdateSettings` (partial patch, validates each value against the group's model, refuses locked keys and unknown keys) and `ResetSetting` (delete the row) as commands via the unit of work. Access: instance settings `Requires(<permission>)` (an admin permission added to the catalogue); user settings `OwnAccount`.
- **Storage:** one table `setting_value(scope, owner_id null, key, value jsonb, updated_at, updated_by)` with a unique key on `(scope, owner_id, key)`; Alembic migration. Unknown keys found at read time (a setting removed in a later release) are ignored and logged. A stored value that no longer validates (constraint tightened) falls back to the next layer and is flagged in the admin view; it never crashes a reader.
- **Reader behaviour:** reads go through a short per-process cache (a few seconds) so a job or request does not hit the DB for every read; a write invalidates the local cache and other processes (the worker) catch up within the TTL. Only fields marked `restart_required` ignore live changes and say so in the UI. `LISTEN/NOTIFY` is a later option, not part of this plan.
- **How a use case reads a setting (prototyped 2026-10-23).** A typed key object lives next to the group that owns the field, and the application layer sees only the port:
  ```python
  @dataclass(frozen=True)
  class SettingKey[T]:
      key: str                                   # "backup.keep_last"

  BACKUP_KEEP_LAST = SettingKey[int]("backup.keep_last")

  class SettingsReader(Protocol):                # application-facing port; in-memory sibling for tests
      async def get[T](self, key: SettingKey[T]) -> T: ...

  keep = await self._settings.get(BACKUP_KEEP_LAST)   # typed int; the use case never knows which layer answered
  ```
  The adapter resolves a key as: pinned by the deployment (`is_pinned`, from the tracked settings) returns the env value; else an instance row, validated on read; else the field default. A stored value that no longer validates falls back to the default and logs which key was invalid. Demo results for `keep_last`: nothing set returns 7; admin saved 12 returns 12; stored 0 (violates `ge=1`) returns 7 with a log line; `MENAGERIST_BACKUP_KEEP_LAST=30` returns 30 even when a row says 12.
  - **Constraint-loss trap:** `TypeAdapter(field.annotation)` drops `Field(ge=1)` and similar, so a bad stored value passes. Validate with `TypeAdapter(Annotated[(field.annotation, *field.metadata)])`. Keep a test for a stored value that violates a constraint.
  - Boot-only settings keep using the `get_*_settings()` getters and never go through the reader. An operation that reads several settings reads once and passes a small snapshot; the reader's short cache covers the rest. The adapter holds the group instances (for pins) and the repository (for rows), so use cases only see the port.
- **Audit:** every write records `updated_by` and `updated_at` and emits a structured log event. A durable audit trail waits for the events work in `2026-10-25-scheduler.md` (stage 2).

### API (indicative; the route restructure is done, so mount under the new `/api/v1/system` layout)
- `GET /api/v1/settings/schema`: one JSON Schema document, properties keyed by setting key, with an `ETag`.
- `GET /api/v1/settings/instance`: for each tunable, `{key, group, scope, value, source, locked, env_name?, restart_required, schema}`. The schema carries `x-menagerist` hints only; state (`source`, `locked`, value) is computed server-side and kept out of it.
- `PATCH /api/v1/settings/instance`: partial `{"values": {key: value}}` body; 404 unknown, 409 locked and 400 invalid, mapped through the existing exception handlers (no try/except in routers).
- `DELETE /api/v1/settings/instance/{key}`: reset to the next layer.
- `GET`/`PATCH /api/v1/settings/me` for user scope (later phase).
- Public config (Part 2 Phase 3) reads fields marked `Public`, independent of this module.

### Cross-stack contract
`shared/contracts/field-kinds.json` lists the field kinds the backend may emit in `UIMeta(kind=...)`; a backend test checks every alias uses a listed kind and a frontend test checks the registry has each one (same pattern as `query-shapes.json`).

## Frontend design

### Extract a reusable core
Today a `FieldTypeDescriptor` mixes what any screen needs with what only the item-type schema editor needs.

| Reusable core (new home, for example `lib/field-types/core`) | Schema-authoring wrapper (stays with the schema editor) |
|---|---|
| `kind`, `label` | `toSchema`, and `fromSchema` returning an `EditorField` |
| shape match and `rank` | `EditorExtras`, `displayOptions` |
| `InputWidget`, `ViewWidget` | `canBeSubField`, `selectable` |
| `formatError`, `formatSummary`, `SummaryWidget` | `searchable`, `highlightable` |

Two registrations keyed by `kind`: the core registry and an authoring registry layered on top. A kind with no authoring half (such as `cron`) is automatically absent from the item-type kind dropdown, replacing the `selectable: false` workaround `opaque` uses. Keep `register(d)` as a facade that registers both halves, so the existing 18 field types change minimally. Keep one matcher: the core asks `fromSchema` (or a shared predicate) so the shape logic does not exist twice.

Steps, each behaviour-neutral with existing tests green:
1. Move `JsonSchemaProperty` and the `x-menagerist` accessors to neutral modules the core can import without the schema editor's types.
2. Split the descriptor type; add the facade; update `registry.test.ts` and the kind-change code to the new shapes.
3. Count and migrate non-editor callers (query builder, search, highlights) to the core imports where it simplifies them.

### Settings form (thin, new)
- Does not reuse `attributes-editor.svelte` (tied to node rows, extra schemas, presets and links); reuses the core registry, the safe validator and `validation-messages`.
- Renders each setting with `descriptorForProp(prop)` and its `InputWidget`; locked settings use `ViewWidget` plus a "set by your deployment (`MENAGERIST_...`)" note.
- Sections per module; title and description from Pydantic; source badge (default, set here, locked); reset-to-default; per-field save (partial patch) with an undo toast, errors mapped through `formatError`. The same component serves the admin instance page and the user page, filtered by scope.
- A new core-only `cron` kind: presets ("daily at 03:00", "off"), validation, and a next-run preview using the instance timezone. Other first settings render from shape alone (integer to number, string to text, boolean to boolean, enum to choice).
- Follow `DESIGN_GUIDELINES.md`; `.svelte` files via `svelte-file-editor`.

## Phases (each shippable alone)

**Phase A: prerequisite (Part 2, prerequisite Phase 1).** Source tracking (`source_map`), `INSTANCE_SETTINGS` logging, secret masking. Needed to know what is pinned.

**Phase B: markers and discovery (backend). DONE 2026-10-28.** Deviations: the markers live in `platform/config/_markers.py` (an architecture test keeps `shared_kernel` free of framework imports); a field is flat when its generated JSON Schema is one scalar or a list of strings, so `ZoneInfo` qualifies; the frontend test for `field-kinds.json` moves to Phase E with the `cron` kind. Discovery is `platform/config/_discovery.py` (`discover`, `SettingSpec`, `SETTING_GROUPS`). Env naming (B.1): `MenageristBaseSettings` owns the `MENAGERIST_` prefix; a subclass declared with `group="backup"` reads `MENAGERIST_BACKUP_<FIELD>` and is keyed `backup.<field>`, so fields need no `validation_alias` (only `TZ`/`MENAGERIST_TIMEZONE` keeps one). Every settings class now has a group (`api`, `backup`, `database`, `identity`, `log`, `media`, `retention`, `scheduler`) and the variables were renamed to match. `UIMeta`, `Tunable`, `Public`, the reusable aliases, group registration, descriptor building, registration tests (flat primitives only, no secrets, kinds in `field-kinds.json`). Annotate the first fields: `BackupSettings.schedule`, `keep_last`, `user_export_ttl_hours`; add `SchedulerSettings.run_history_per_job`. No behaviour change yet.

**Phase C: frontend core extraction. DONE 2026-10-28** (steps 1-3; the `field-kinds.json` frontend test moves to Phase E with the `cron` kind). `lib/prop-meta.ts` and `lib/json-schema.ts` hold the neutral accessors and types (old paths re-export them); `field-types/core.ts` holds `FieldCore`, the single matcher `pickCore` and `coreForProp`/`getCore`/`allCores`/`registerCore`; `registry.ts` keeps the schema-editor half and `register()` registers both, so the 18 field types are unchanged. Render-only callers use `coreForProp`; `GroupInput.svelte`, the schema editor and the kind row stay on the descriptor. Steps 1-3 above, plus `field-kinds.json` and its two tests. Independent of A and B and worth doing even if the settings UI slips.

**Phase D: settings module backend. DONE 2026-10-28** (instance scope; user-scoped routes and use cases stay in Phase G, but the repository, reader and resolution are already scope-aware). Built in four slices: D1 domain, ports, in-memory adapters and `CachedSettingsReader` with the `SettingKey`/`SettingsReader` port in `shared_kernel` (question 7); D2 `setting_values` table (`KEEP` in backups), SQL upsert repository and `build_catalogue` from `discover()` plus the live settings instances (pins); D3 `ListSettings`, `GetSettingsSchema`, `UpdateSettings`, `ResetSetting` and the admin-only `settings:instance:read`/`write` permissions; D4 the API. Deviations: a domain `ValidationError` is a 400, not 422; the PATCH body is `{"values": {key: value}}` because request models must be `RequestModel`s with named fields; cross-field validation of a patch (question 9) is deferred until a tunable group has a constraint spanning two tunable fields; the common error responses are now inlined per operation so each example cites its own URL.

Original scope: Domain, ports, in-memory siblings, migration, use cases, `SettingsReader`, API routes, contract-style tests for the repository (in-memory and Postgres), router tests, locked and invalid cases, cache behaviour.

**Phase E: settings form and `cron` kind (frontend).** Admin instance page, source badges, reset, per-field save, the `cron` core kind.

**Phase F: wire the first consumers.** The scheduler's `ScheduleSource` adapter reads `backup.schedule` through `SettingsReader` (env pin still wins). Update-check enable switch and run-history size become tunable. Retention settings follow.

**Phase G: user scope.** `/settings/me`, user-scoped descriptors (display timezone, locale first), and the user-deletion decision (FK cascade versus an event; Part 2 Q9).

## Tests
- Unit: marker merge behaviour, discovery over nested aliases, pin and source resolution, precedence (default, instance, user, env), partial patch, locked and unknown keys, stale stored values, cache TTL and invalidation. 100% in domain and application.
- Registration guards: flat primitives only, no secret types, every `UIMeta.kind` in the contract, every `Tunable` field has a title.
- Source tracking: init, env, dotenv and secret-file labels; env beats dotenv; default when unset; prefix, full-name-alias and `AliasChoices` fields; an override that drops dotenv and adds a custom source; an override that calls `super()` (no double wrapping); a child class inheriting an override; `.env` values not labelled `env`.
- Reader: precedence (pin, row, default), stored value violating a constraint falls back, unknown stored key ignored, typed key returns the field's type.
- Frontend: registry core tests, authoring facade parity (all existing kinds still register both halves), settings form states (default, set, locked, invalid, reset), `cron` widget.
- Integration (`@pytest.mark.integration`): the repository against Postgres; one end-to-end: env-pinned key stays locked while another is edited.

## Risks
- Two sources of truth if a descriptor is also written by hand: the plan allows none; the model fields are the only declaration.
- Splitting the registry touches every field type; the facade and unchanged tests keep the blast radius small. The shape matcher must stay single.
- Stale cache across API and worker: bounded by the TTL; schedules are read each tick, so a change takes effect within about a minute.
- Pydantic emits `anyOf` for optionals, which the descriptors do not match (they check `prop.type`); the flat-primitives rule and the registration test avoid it.
- Alias handling: schemas must be built with `by_alias=False` and env names derived from `validation_alias` or the prefix; source tracking has the same translation concern (handoff finding 4).
- Operators who set an env var "just once" lock a setting forever; the UI must say so clearly and name the variable.

## Open questions
1. Which permission name guards instance settings (new `system:settings:write`, or reuse an existing admin permission)?
2. Central group list or auto-discovery?
3. Versioning of setting values: last write wins, or an ETag per key? (Single-admin installs make last write wins reasonable.)
4. Which settings beyond the first four should be tunable (session TTLs, upload limit, update-check switch)? Several overlap with public config.
5. User settings first picks, and the user-deletion mechanism (Part 2 Q9).
6. Does the admin page live under Settings with the existing admin sections, and what is it called in the UI?
7. Where do `SettingsReader` and `SettingKey` live? Other modules' use cases must read settings and modules do not import each other, so the port belongs in `shared_kernel` (implementation in `modules/settings`, wired in the composition root).
8. Scope rule: each key has exactly one scope, so the chain is env pin, DB row, default. Confirm, and drop "user row above instance row".
9. Partial `PATCH` validates the patch merged into the group's current effective values, so model-level validators run.
10. Policy for `updated_by` on user deletion, and whether `setting_value` is included in backups and restores.
11. Permission name: follow the `scheduling:job:*` convention (for example `settings:instance:write`), and settle the route prefix (`/api/v1/settings/...` versus under `/api/v1/system`).

## Order across both documents

1. CSRF plan: done (Sam, 2026-10-23).
2. Part 2 prerequisite Phase 1 (source tracking and logging). Phase 2 (route restructure) is done. Phase 3 (public config) only when a screen needs a value.
3. Scheduler Phases 0-3 (verify, domain and in-memory adapters, Postgres adapter and worker, scheduled backups); they need no DB-backed settings.
4. Phase C of this plan (frontend field-type extraction) any time; Phases B, D and E after Part 2 Phase 1.
5. Scheduler Phases 4-6 and Phase F of this plan once the pieces exist.

Other plans: `2026-10-20-access-model-refactor.md` (its Q4 is answered by the existing `System` stance) and `2026-10-20-api-tokens-and-permissions.md` (expired-token purge is a scheduler job; the admin permissions for jobs and settings join its catalogue).

# Part 2: prerequisites (from the earlier settings handoff plan)

Startup logging of deployment config, the system route restructure and public config. The CSRF cookie work it referred to is done.

## Kinds of settings

| Kind | Source | Home | Editable at runtime | Visible to |
|---|---|---|---|---|
| Deployment config | env, `.env`, secrets dir | `platform/config` (exists) | no | operators |
| Public config | subset of deployment config, explicitly marked | `modules/system` query, `/api/v1/system/public-config` | no | anyone, read-only |
| Instance settings | database | new `settings` module (this document) | admins | admins edit; public subset readable |
| User settings | database, per user | same module, user scope | that user | that user |

## Findings that shape the plan

1. **CSRF cookie name mismatch: superseded.** The backend default was `menagerist-csrf` and the frontend used `menagerist_csrf`, so signed-in unsafe requests got `csrf_failed`. `2026-10-20-csrf-origin-protection.md` (PR 1) removes the CSRF cookie, header and `csrf_cookie_name` setting, so there is nothing left to align or to publish through public config. Do not add a CSRF field to public config.
2. **`DatabaseSettings.database_url` is a `PostgresDsn` whose default contains a password.** Logging the group as is would leak it. `SecretStr` would break call sites that use it as a URL.
3. **Route mounting today** (`entrypoints/api/__init__.py`): `/api` holds `system_router` (health, version) and `docs_router` unversioned; `api_v1_router` (`/api/v1`) is authenticated; `public_v1_router` (`/api/v1`) is unauthenticated and holds only `public_auth_router`. `/health` is used by the Docker `HEALTHCHECK`; `/health/ready` and `/health/ready/detail` are used by `frontend/src/lib/status.ts`.
4. `MenageristBaseSettings` is `frozen=True, validate_default=True` with `env_prefix="MENAGERIST_"`. `BackupSettings` uses full-name `validation_alias`es, so any tracking must translate aliases back to field names.
5. **Interaction with the CSRF PR: resolved.** The CSRF work is done (Sam, 2026-10-23), so `csrf_cookie_name` is gone from `IdentitySettings` and the Phase 1 `INSTANCE_SETTINGS` logging never sees it. (Not re-checked in the repo; my clone predates the change.)

## Decisions already made

- Instance settings are logged at startup: deployment config first (values plus source, secrets masked), DB instance settings after the DB is reachable (skipped quietly if not, like `warn_if_no_administrator`).
- Secrets use pydantic `SecretStr` (renders `**********`). The DSN gets a serializer that masks the password in JSON/log mode only; Python mode still returns the real value so the engine is unaffected.
- Public fields are opt-in (marker on the field), never "everything minus secrets". As of 2026-10-23 the marker is a `Public()` annotation (see this document), which resolves Q5.
- Probes (`/api/health`, `/api/health/ready`) stay unversioned. Everything else in the system section moves under `/api/v1/system/...`. Unauthenticated routes (version, public config) mount on `public_v1_router`; the two `/detail` routes mount on `api_v1_router`.
- Public config: `GET /api/v1/system/public-config`, operation id `get_public_config`.
- First public fields: `media.max_upload_size`; optionally `identity.session_ttl_hours` and `session_idle_hours`. Sign-in throttle numbers, paths, `trusted_proxies`, `database_url`, hasher settings, cleanup TTLs and backup retention stay private. (`identity.csrf_cookie_name` was in this list and is removed: the setting no longer exists.)

## Phases (each is independently shippable; stop for questions at the checkpoints)

### Prerequisite phase 1: startup logging of deployment config
- New `platform/config/_tracking.py` with a tracked base class (prototyped and tested 2026-10-23: 4 tests in the sandbox; the prototype is not in the repo):
  - `settings_customise_sources` wraps each of the four standard sources (`init`, `env`, `dotenv`, `secret_file`) in a thin recorder that notes which keys that source supplied. Sources arrive highest priority first, so the first to supply a key wins. A `ContextVar` collector (not a module global) is set per construction, and `__init__` stores the result in a private `_sources` attribute, so the model stays frozen.
  - Public surface on the base: `source_of(field) -> "init" | "env" | "dotenv" | "secret_file" | "default"`, `is_pinned(field)` (true for env, dotenv and secret file) and `sources()`. No dunder name (`__sources__` is reserved style).
  - Alias fields are mapped back to field names: prefix style (`backup_path`), full-name aliases (`MENAGERIST_BACKUP_KEEP_LAST`) and `AliasChoices("MENAGERIST_TIMEZONE", "TZ")` all report correctly..
  - Subclass overrides are tracked automatically: a `@tracked_sources` decorator wraps whatever an override returns (already-wrapped sources are left alone, so `super()` calls are not double-wrapped), and `__init_subclass__` applies it to any subclass that defines its own `settings_customise_sources`. Custom sources report their `source_label` attribute, else their class name.
  - Label lookup must test the most specific class first: `DotEnvSettingsSource` subclasses `EnvSettingsSource`, so the wrong order labels `.env` values as `env` (found and fixed in the prototype; keep a test for it, because the mistake would falsely lock dotenv values as env-pinned).
  - Optional later: report which env var supplied a value, for the UI's "set by `MENAGERIST_...`" note.
- Make `MenageristBaseSettings` extend the tracked base; confirm `frozen` and `validate_default` still work with the private `_sources` attribute (not a field, so it is excluded from dumps and repr).
- Mask `database_url` (JSON-mode serializer). Add an `INSTANCE_SETTINGS` tuple in `platform/config/__init__.py` listing every getter (one line per group).
- `log_instance_settings()` in `entrypoints/api/startup.py`, called from `lifespan` beside `warn_if_storage_not_writable`. One structlog event per group: field, value (`model_dump(mode="json")`), source (`default` when no source recorded).
- Tests: tracking unit tests (inherit, replace order, extend via super, alias fields like `BackupSettings.before_migrate`); a test that no logged field with a secret-looking name (`password`, `secret`, `token`, `key`) is a non-secret type; a log-output test asserting the DSN password never appears. Platform floor is 70%.
- **Checkpoint Q2:** log level and format (one event per group at INFO, or one combined event)? Should defaults be logged or only explicitly set fields?

### Prerequisite phase 2: restructure the system routes under /api/v1/system (DONE, Sam, 2026-10-23; not re-checked in the repo, so confirm the final paths and operation ids before relying on them)
- Split `modules/system/adapters/api/router.py` into a root probes router (`/health`, `/health/ready`) and a versioned system router. Keep operation ids so generated client method names do not change.
- Mount: `/health/ready/detail` and `/version/detail` on `api_v1_router`; `/version` on `public_v1_router`.
- Update path references: `frontend/src/lib/status.ts`, `entrypoints/api/docs/static/swagger-init.js` if it lists paths, backend and frontend tests that call these routes; regenerate the client (`poe generate-frontend-client`).
- **Checkpoint Q3:** keep deprecated aliases at the old detail paths for a release? Default answer: no (pre-stable `0.` versioning, no known external callers).
- **Checkpoint Q4:** is anything outside this repo (monitoring, scripts) calling `/api/health/ready/detail` or `/api/version`?

### Prerequisite phase 3: public config
- Marker on the field: the `Public()` annotation from this document (Q5 resolved; the typed annotation, as originally recommended).
- Registration guard: a public field may not be `SecretStr`/`SecretBytes` or a URL with credentials; enforced in a unit test over all registered groups.
- `modules/system`: `GetPublicConfig` query (no UoW), port `PublicConfigSource`, platform adapter reading the marked fields from the cached settings, `in_memory_` sibling, typed response model, router on `public_v1_router`, short `Cache-Control` plus ETag (`shared_kernel/etag.py`).
- Tests: response contains exactly the allowlisted fields; adding an unmarked field does not change the response; ArchUnit tests still pass.
- Frontend (via `svelte-file-editor` where `.svelte`): fetch once at boot where a screen needs a value (for example the upload limit). Nothing in `auth.ts` depends on it any more, because the CSRF cookie name is gone.
- **Checkpoint Q6:** include session lifetimes (for a "signed out in..." hint)? Include `backup.max_upload_size` (admin-only screen, so arguably better behind auth)?
