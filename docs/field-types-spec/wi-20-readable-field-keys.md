# WI-20: Readable, immutable field keys

> Part of the field-types spec. Read `00-INDEX.md` and `01-context-and-conventions.md` first (skip the second if this is that file).
> **Depends on:** WI-14. Land before any item that creates fields (WI-5, WI-18, WI-19).
> "WI-n" refers to `wi-*.md` files listed in `00-INDEX.md`; "open question N" refers to `open-questions.md`.


**Goal.** A node's `attributes` should be readable without knowing the schema: `{"director": "Ridley Scott", "year": 1979, "my_rating": 5}` instead of a map of UUIDs. That also makes the API, search context, exports, purge and usage endpoints (WI-9) and any third-party consumer easier to work with.

**Why the keys are UUIDs today (reconstructed).** `generateKey()` in `schema-editor.svelte` returns `crypto.randomUUID()`. `docs/DECISIONS.md` records UUID7 entity ids but has no entry for field keys, so the reasons are not written down. The stability requirements the design was built around are:
1. Renaming a field's label must not touch stored data.
2. Keys must never collide, including when a title is reused or two fields share a title.
3. Archive and restore must reattach data to the right field, and every reference by key (layout, `required`, `highlights`, `origin`) must stay valid.

Confirmed as complete by the owner; nothing else was being protected.

**Decision: the key is the slug of the title *at creation time*, then immutable.** Readable, but decoupled from the label afterwards. Renaming the label never changes the key, so requirement 1 holds exactly as it does with UUIDs. This is the usual pattern (NetBox, for example, keeps a raw field `name` used in the database and API separate from its human-friendly `label`).

**Generation rules.**
- Take the title, apply the repo's `slugify` (NFKD, ASCII only, lowercase), turn hyphens into underscores, and cap at 40 characters. Only `a-z`, `0-9` and `_` remain, which is safe in URLs (the WI-9 `.../attribute/{key}/...` routes), in JSON path, and as `attrs.key` in JavaScript, where hyphens are not.
- An empty result (a title that is entirely non-Latin or punctuation) becomes `field`.
- If the key already exists in the schema's `properties` (archived fields included), append `_2`, `_3`, and so on. The comparison is case-insensitive. A new field titled "Director" next to an archived "director" becomes `director_2`, so it can never revive hidden data.
- Verified with the repo's `slugify`:

| Title | Key |
|---|---|
| Director | `director` |
| My rating | `my_rating` |
| Signed? | `signed` |
| Track no. | `track_no` |
| Año de estreno | `ano_de_estreno` |
| Price (£) | `price` |
| 監督, # | `field` (then `field_2`, ...) |

- Group sub-fields use the same generator, unique within their group. Layout containers (sections, rows, tabs) keep opaque ids; they are not attribute keys.
- Nothing in the app may parse meaning out of a key; it stays an opaque identifier.

**Rules that keep stability.**
- The key is **not shown in the normal UI**: the design guidelines forbid exposing internal field identifiers and say to derive the key from the label without surfacing it (§16, §16a). There is no developer view of keys in v1 (decided).
- Removing a field is still archive-first (WI-8). A field that is fully removed and whose data is purged frees its key. A field removed from the schema *without* purging (for example through the API) leaves orphaned data under its key; re-adding a field with the same title later gets the same key and **reattaches that data**. That is arguably a feature (undo); it is accepted (decided) and documented as a difference from UUIDs.
- When adding a field, check the new key against custom detail names already in use on that item type (the WI-18c custom-names query, case-insensitive). On a match, offer to adopt those values rather than silently capturing them, so an existing custom "Director" detail is not reinterpreted as a typed field by accident.
- Presets (WI-19) generate keys with the same generator against the target schema, so a preset can be added twice without clashing.

**Trade-offs versus UUIDs (accepted).**
- The key can drift from the label after a rename (key `director`, label "Filmmaker"). Mitigation: the optional explicit key change below.
- Reattachment of purged-less orphans, described above.
- Two people adding the same-titled field concurrently: the ETag on `PATCH /node-type/{id}` already rejects the second write, which then re-reads and gets `_2`.
- Keys are unique per item type, not globally. That is fine because attributes are per node and a node's type cannot change once set; if a type is deleted, the readable keys become useful custom details.

**WI-20b: "Change key" action (dropped from v1, decided).** It needs the key to be visible to the user, which conflicts with the guidelines, and it has no concrete driver yet. An advanced action that rewrites a field's key everywhere in one transaction: the schema property and every reference to it (layout, `required`, `highlights`, `origin`), and each node of the type through the unit of work (skipping nodes that already have the target key, and reporting them). It is the same operation as WI-18c's adopt, where the source key is a custom detail instead of a schema field, so consider one command, `RekeyNodeTypeAttribute`, serving both (open question 37).

**Existing data.** No migration. Keys are opaque strings, so UUID-keyed fields keep working; new fields get slug keys; a schema may mix both. The backend needs no change: it never generates keys, and keys already accept any string (WI-18a adds the name-length and blank-name limits). Add a `docs/DECISIONS.md` entry for the key rule.

**Where else the spec changes.** WI-15's example uses `"cover_file"`, WI-16's highlights example uses `"director"` and `"my_rating"`, WI-18b and WI-19 say "new key" instead of "new UUID key", and `example-node-type-schema.json` is regenerated with readable keys.

**Acceptance.**
- A new field titled "Director" gets the key `director`; renaming its label to "Filmmaker" leaves the key `director` and every stored value in place.
- A second field titled "Director" gets `director_2`; a field titled "Director" next to an archived `director` also gets `director_2`.
- A non-Latin title produces `field`, then `field_2`.
- A schema with UUID-keyed and slug-keyed fields loads, edits and validates normally.
- A node's `attributes` dict for a slug-keyed type can be understood without the schema.

**Tests.**
- Unit (frontend): the generator (Latin, accented, punctuation, non-Latin, long titles, reserved names such as `constructor`), uniqueness against archived keys and case-variants, label rename keeps the key, group sub-field uniqueness.
- The "adopt existing custom detail" prompt when a new key matches a custom name in use.
- Contract fixture: the Vinyl example uses readable keys, so both suites exercise them.
- Integration: JSONB search, usage and purge queries with underscore keys behave as they do with UUIDs (they treat keys as opaque bound parameters).
- Editor code that builds `properties` must not assign through a user-controlled key (`properties[key] = ...`) for names such as `__proto__`; use `Object.fromEntries` or a `Map`. Generated keys cannot start with an underscore, but custom detail names and API-authored keys can.
