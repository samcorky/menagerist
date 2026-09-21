# WI-15: Text constraints, starts with and ends with

> Part of the field-types spec. Read `00-INDEX.md` and `01-context-and-conventions.md` first (skip the second if this is that file).
> **Depends on:** WI-1 (empty-string omission), WI-4, WI-14.
> "WI-n" refers to `wi-*.md` files listed in `00-INDEX.md`; "open question N" refers to `open-questions.md`.


**Goal.** Let a text field require a prefix and/or a suffix (for example a cover file that must start with `cover-` and end with `.jpg`, or a catalogue number that must start with `LP-`). Friendly to configure, enforced identically by the client and the backend.

**Storage: standard JSON Schema, not `x-menagerist`.** These constraints affect validity, so by the WI-14 principle they are standard keywords: anchored `pattern`s, one per constraint.

```json
"cover_file": {
  "title": "Cover file",
  "type": "string",
  "allOf": [
    { "pattern": "^cover-" },
    { "pattern": "\\.jpg$" }
  ],
  "x-menagerist": { "kind": "text" }
}
```

- One constraint: emit a single `pattern` (`"^cover-"`). Both: emit an `allOf` of two `pattern` subschemas. Do not combine them into one regex with lookaheads or `.*`; a single `^a.*a$` would wrongly reject a value of `a` and error messages could not say which half failed.
- The pattern is the single source of truth (no duplicated copy in `x-menagerist`). `text.fromSchema` recovers "Starts with" / "Ends with" by parsing exactly the forms the writer emits: `^` + escaped literal, and escaped literal + `$`. Any other `pattern` or `allOf` content is not touched by the editor: carry it through unchanged (the same lossless-passthrough mechanism as WI-4) and show a small "custom pattern" note.
- Applies to `text`, including text sub-fields inside a group. Not `longtext` (multi-line anchoring is ambiguous), not other kinds.
- Case-sensitive only. Case-insensitive matching is not expressible in a portable pattern (no flags in JSON Schema); see open questions.

**Escaping (verified).** `@cfworker/json-schema` compiles patterns with the `u` flag, so an unnecessary escape such as `\-` throws `Invalid regular expression`, while Python's `re` accepts it. Escape only the regex syntax characters `\ ^ $ . * + ? ( ) [ ] { } | /` and never `-`. Test with awkward literals (`.`, `/`, `(`, `\`, `-`, unicode and emoji).

**Two regex engines (verified).** The same `pattern` is checked by two different engines:

- Backend: Python `jsonschema` (4.26 tested; the repo allows `>=4.23`) runs `re.search(pattern, value)`, which is Python's own `re` dialect.
- Frontend: `@cfworker/json-schema` runs `new RegExp(pattern, 'u')`, the ECMA-262 dialect that the JSON Schema spec itself names as the reference.

Outputs from the same patterns in both engines:

| Pattern | Python `re` | JavaScript (`u`) |
|---|---|---|
| `a$` against `"a\n"` | matches | no match |
| `^\d$` against `٣` (Arabic-Indic digit) | matches | no match |
| `\p{L}` | error | works |
| `(?i)abc` (inline flag) | works | error |
| `(?P<n>a)` (named group) | works | error |
| `(?<n>a)` (named group) | error | works |

Two consequences beyond disagreement: an invalid pattern makes `@cfworker/json-schema` **throw** from `validate()` (it does not return an error), so one bad pattern in a schema would break the whole attributes form; and a user-supplied regex evaluated by Python's `re` on the server has no timeout, so it is a ReDoS risk.

**Handling it: generate, don't accept (recommended).**
1. **Structured constraints first.** Users never type a regex. Starts with, ends with, and any later constraints (contains, min/max length, presets such as digits only) are compiled to patterns by one escaping function. Patterns built from literal text, escaped syntax characters, `^` and `$` behave identically in both engines, apart from the trailing-newline case above. This is what WI-15 already does.
2. **Free-form regex, only if power users really need it (open question 13).** Accept a *portable subset* only, enforced when the schema is saved:
   - Allowed: literals and escaped syntax characters, `.`, character classes with explicit ASCII ranges (`[0-9]`, `[a-z]`), `^` `$`, the quantifiers `*` `+` `?` `{n}` `{n,m}`, groups `( )` and `(?: )`, and `|`.
   - Rejected: lookaheads and lookbehinds, backreferences, named groups, inline flags, `\p{..}`, and the shorthands `\d \w \s \b` and their negations (they differ between engines; use `[0-9]` etc.), nested unbounded quantifiers such as `(a+)+` (ReDoS), and patterns over a length limit (for example 200 characters).
   - Enforcement: a small tokenizer, not a full regex parser. The backend copy is authoritative (`InvalidSchemaError` on node-type and edge-type save); a frontend mirror gives instant feedback in the schema editor.
3. **Defence in depth for schemas the editor did not write** (for example authored through the API):
   - Backend: `UpdateNodeType` already runs `check_schema`, and with `jsonschema` 4.26 that rejects patterns Python cannot compile (verified: `[` and `(?<n>a)` both raise `SchemaError`, which becomes `InvalidSchemaError`), including nested ones. Confirm the same holds for the locked version and for create/edge-type handlers, and lock the behaviour with a test. Only the portable-subset check (if free-form regex ships) is new, and it belongs in one shared helper used by all four type handlers.
   - Frontend: wrap `Validator` construction and `validate()` in try/catch. A pattern that JavaScript rejects must degrade to a visible schema warning and skip that constraint, never break the form.
   - Schema editor: compile the pattern with `new RegExp(p, 'u')` before allowing the save.
4. **One shared conformance fixture.** A JSON file of `{pattern, value, expected}` cases plus accepted and rejected subset examples, checked into the repo and loaded by both the vitest and pytest suites. If an engine upgrade or a new rule makes them disagree, CI fails. WI-15's generated patterns must pass the subset check too.

Alternatives considered and rejected: validating on the server only (loses instant feedback in the form); running one engine on both sides (there is no ECMA-262 engine for Python, and shipping a Python engine to the browser is heavy); switching the backend to `google-re2` (linear-time and safe, but its syntax is a third dialect; worth revisiting only if free-form regex ships and ReDoS becomes a real concern).

**Empty values (verified).** `''` fails an anchored pattern even on an optional field. WI-1's "omit empty" rule is extended above to cover text properties with a `pattern`.

**Editor UX.** Progressive disclosure: a collapsed "Validation (optional)" section on the text field in the schema editor, with two inputs, "Starts with" and "Ends with". Implement it as the text descriptor's `EditorExtras`. In the attributes editor, show the rule as helper text under the input (for example: Must start with `cover-` and end with `.jpg`).

**When errors appear.** Show constraint messages on blur or save, not on every keystroke (guidelines §15).

**Error messages.** The raw validator message is unfriendly ("String does not match pattern."). Both validators report the failing keyword and its location (cfworker `keywordLocation` ends in `.../allOf/0/pattern`; Python `jsonschema` exposes `validator == 'pattern'` and `validator_value`). Translate from the pattern itself, not from its index: a pattern of the `^literal` form becomes `Must start with "literal"`, and `literal$` becomes `Must end with "literal"`. Put the translation behind a descriptor hook (for example `formatError?(error, prop)`), and have the API return the keyword and value in its validation error detail so the client can translate server-side failures too.

**Interactions.**
- WI-7 (changed keys only): a stored value that no longer matches a newly added prefix does not block saving other fields; editing that field re-validates it.
- WI-10: changing an existing text field to add a constraint should warn with a count of nodes whose value would fail (same count mechanism as removed choice options).
- Known edge: Python's `$` also matches before a trailing newline while ECMA-262's does not. Text values from the UI are single-line, so accept the difference, and note it in the docs.

**Acceptance.**
- Configuring a prefix and a suffix on a text field, then saving, produces the schema shown above and reloads showing the same two inputs.
- A value missing the prefix shows `Must start with "cover-"` under the field, and the backend rejects the same value.
- A cleared optional constrained field saves without error.
- A pattern the editor did not write survives open-edit-save unchanged.

**Tests.** Escape and unescape round-trip for tricky literals; prefix only, suffix only, both, and both identical; `allOf` ordering does not matter for messages; cfworker does not throw on any generated pattern (guards against `\-`); Python `jsonschema` and cfworker agree on the shared conformance fixture (see above); generated patterns pass the portable-subset check; a JavaScript-invalid pattern in an API-authored schema degrades to a warning instead of breaking the form; the backend rejects an uncompilable pattern on schema save; empty-string omission; group text sub-field; custom pattern preserved; friendly-message translation.
