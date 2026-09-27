# WI-27: URL, Email and Phone field kinds

> Part of the field-types spec. Read `00-INDEX.md` and `01-context-and-conventions.md` first (skip the second if this is that file).
> **Depends on:** WI-4 (`opaque` fallback for an unrecognised shape - the safety net if a format value this app doesn't know is ever encountered), WI-15 (pattern/friendly-error machinery, reused directly by `phone`).
> "WI-n" refers to `wi-*.md` files listed in `00-INDEX.md`; "open question N" refers to `open-questions.md`.
> **Status:** proposed, not yet implemented. Promoted from `further-field-types.md`'s "URL / Email / Phone" candidate row on direct request.

**Motivating case.** A website, an email address, a phone number - each already fits comfortably as a scalar string with a format or pattern; the only reason they're not just `text` is that they display better as a clickable `mailto:`/`tel:`/external link and deserve their own friendly kind label rather than every user reinventing a text-constraint pattern for the same thing.

**Three separate kinds, not one.** Each has a distinct stored shape and a distinct link behaviour in view mode, so they register separately (matching this spec's own precedent: `list`/`checklist` share a shape family but are separate kinds, not variants of one kind).

**`url`:**
```json
"website": { "title": "Website", "type": "string", "format": "uri", "x-menagerist": { "kind": "url" } }
```
**`email`:**
```json
"contact_email": { "title": "Contact email", "type": "string", "format": "email", "x-menagerist": { "kind": "email" } }
```
**`phone`:**
```json
"phone_number": { "title": "Phone number", "type": "string", "pattern": "^[0-9+()\\-\\s]{3,32}$", "x-menagerist": { "kind": "phone" } }
```
`phone` has no native JSON Schema format keyword, so it is exactly the existing `pattern` variant `text` already uses (WI-15) - no new schema shape, just a distinct `kind` and a permissive default pattern (digits, `+`, `()`, `-`, spaces; wide enough for international numbers without validating a specific country's format). `url` and `email` need `schema-types.ts`'s `JsonSchemaPropertyBase` string-with-`format` union member widened from `format: 'date'` only to `format: 'date' | 'uri' | 'email'`.

**Validation (decided, matching this app's existing `format` posture):** `format` is an annotation, not an enforced assertion, in this codebase's JSON Schema validator setup today (`date` already works this way - an invalid date string is not rejected by `format` alone). `url`/`email` follow the same posture in v1: no client- or server-side format enforcement beyond "is a string", same looseness WI-24's `quantity` unit and this file's own `phone` pattern already accept. A future session can add real `format: 'email'`/`format: 'uri'` assertion if wanted; not scope here.

**In the app.**
- **Entering:** a plain text input per kind (`<input type="url">` / `type="email">` / `type="tel">` for the right mobile keyboard and basic browser-native hinting, no custom validation beyond that).
- **Viewing:** `url` renders as an external link (`<a href={value} target="_blank" rel="noopener noreferrer">`); `email` as `<a href="mailto:{value}">`; `phone` as `<a href="tel:{value}">`. Empty renders `-`, matching every other empty-field convention.
- **Highlights (WI-16):** all three highlightable; `formatSummary` is just the raw string (same as `text`).
- **Search (WI-17):** works for free - all three are top-level string values, already covered by the existing scalar scan.
- **Sub-field use:** `canBeSubField: true` for all three from v1 - they're plain strings, no object-cell prerequisite applies (unlike `quantity`/`money`).
- **Registration order:** all three must register before `text` in `index.ts` (each is a `string`-shaped fallback match that `text`'s own `fromSchema` would otherwise also claim when no explicit `kind` is present) - same precedent `docs/field-types.md`'s own worked `url` example already documents.

**Backend:** nothing new - plain string in the existing `attributes`/`attributes_schema` column, no port, no migration. `format`/`pattern` pass through the existing JSON Schema validation path unchanged (annotation-only for `format`, already-enforced for `pattern` since `text` uses it today).

**Acceptance.**
- Each of the three kinds round-trips through `toSchema`/`fromSchema` unchanged, matched by its own `format`/`pattern` plus `kind`.
- An unrecognised `format` value (something other than `date`/`uri`/`email`) still falls back to `opaque` (WI-4), not a crash.
- Each kind's view mode renders the correct link type (`mailto:`/`tel:`/external) and each is highlightable and searchable.

**Tests.** Unit: `toSchema`/`fromSchema` round-trip for each of the three kinds; the `opaque` fallback for an unknown `format`; view-mode link rendering (three cases) and the empty-value `-` case. Contract fixture: add one example of each (for instance `website`, `contact_email`, `phone_number`) to `example-node-type-schema.json`.
