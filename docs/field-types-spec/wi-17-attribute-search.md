# WI-17: Searching attribute values

> Part of the field-types spec. Read `00-INDEX.md` and `01-context-and-conventions.md` first (skip the second if this is that file).
> **Depends on:** WI-8 (archived exclusion) and WI-14 (`search` member).
> "WI-n" refers to `wi-*.md` files listed in `00-INDEX.md`; "open question N" refers to `open-questions.md`.


**Decision.** Search scans **all** attribute values, in some form, not only highlighted ones. Highlights (WI-16) are display only.

**Current state (verified in `node_repository.py`).**
- `q` matches `name` and `description` only, in both `list` and `count`. Attributes and tags are not searched.
- The pattern is `f"%{q}%"` with no escaping, so `%` and `_` typed by the user act as wildcards (confirmed in Postgres: `%` alone matches every row).

**Proposed behaviour.** `q` also matches any scalar **string or number value anywhere inside `attributes`**, including cells inside group rows, as a case-insensitive substring like today. It never matches key names, booleans or nulls. Per node type it skips:
- archived fields (WI-8). Otherwise search would find a node because of a value the user can no longer see;
- fields with `x-menagerist.search: false` (a per-field opt-out for noisy fields; default is searchable);
- kinds that declare `searchable: false` (boolean and rating in v1; a new optional descriptor member, default `true`).

Untyped nodes are scanned in full. Values stored under keys that the schema does not define are visible to users under "Additional details", so they are searched.

**Query.** Verified against PostgreSQL 16 (the repo targets 18):

```sql
EXISTS (
  SELECT 1
  FROM jsonb_path_query(attributes - :excluded_keys, 'strict $.**') AS v
  WHERE jsonb_typeof(v) IN ('string', 'number')
    AND (v #>> '{}') ILIKE :pattern ESCAPE '\'
)
```

Per type, `:excluded_keys` is that type's list; build one clause per type that has exclusions (`type = 'film' AND scan(attributes - ARRAY[...])`), plus a final clause for every other type and for untyped nodes that scans `attributes` unchanged. The number of types is small. Keys and the pattern are bind parameters, never interpolated (keys come from user-authored schemas).

Checks I ran on real Postgres: a value inside a group row is found; a string that exists only as a key name is not found (unlike `attributes::text ILIKE`, which matched every row on key text and is rejected); `1979` finds a numeric year; searching `true` does not match a boolean; `attributes - ARRAY['k_old']` hides an excluded field's value; `ESCAPE '\'` makes a `%` in the query literal.

**Ports and handler.**
- `NodeRepository.list` and `count` gain an optional `attribute_search_exclusions: Mapping[str, Sequence[str]] | None = None` (type slug to top-level keys to skip), used only when `q` is set. SQLAlchemy adapter as above; in-memory adapter walks the values recursively with the same rules.
- `ListNodes` builds the mapping from node types using a WI-14 backend accessor `search_excluded_keys(schema)` (archived, `search: false`, non-searchable kinds). It needs `repos.node_types` in addition to `repos.nodes`; this is one small extra query per search.
- Escape `%`, `_` and the escape character in `q` for the existing name and description match too. That is a small existing bug fixed in the same change.
- **No API change:** same `q` parameter, same response. Describe the new semantics in the OpenAPI description.

**Result context (frontend only).** A node can now match on a value that is not visible on its card. Search results therefore show why it matched when the match is not in the name or description, for example "Matched in Director: Ridley Scott", using the already-loaded attributes and the schema's field labels. For group cells show the group field's label and the matching cell text. Highlighted fields (WI-16) keep showing as usual.

**Ordering and scale.**
- Results stay in id order with the existing keyset pagination. Relevance ranking would need a different cursor and is out of scope.
- The query-time scan is a sequential scan. Measure it with a few thousand and tens of thousands of nodes before deciding it is a problem.
- Later, without changing the port, a maintained `search_text` column with a `pg_trgm` GIN index (or `tsvector`) can replace the scan. It needs reindexing whenever a schema change alters what is searchable (archive, opt-out), which is why v1 is query-time.

**Acceptance.**
- Searching for a director's name finds the film even when that field is not highlighted.
- Searching `Ripley` finds a node whose only match is inside a group row.
- Searching `true` or a hex fragment of a field key finds nothing extra.
- Archiving a field stops its old values matching. A field with `search: false` never matches.
- `%` typed as a search term matches only literal `%`.

**Tests.**
- Unit (in-memory repository, handler): string, number, nested group cell, boolean and null ignored, keys ignored, archived and opt-out exclusions, untyped nodes, escaping.
- Integration `I-7` (real Postgres): the same cases as the verified checks above, plus type scoping (the same key text in another type is not excluded) and `count` agreeing with `list`.
- Frontend: match-context helper for name, attribute and group-cell matches.
- End-to-end: search by an attribute value from the collection page.
