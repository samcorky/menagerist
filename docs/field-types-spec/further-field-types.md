# Further field types and the location kind

> Part of the field-types spec. Read `00-INDEX.md` and `01-context-and-conventions.md` first (skip the second if this is that file).
> **Type:** reference file of candidate kinds; none is scheduled. The location kind depends on WI-14 and WI-20.
> "WI-n" refers to `wi-*.md` files listed in `00-INDEX.md`; "open question N" refers to `open-questions.md`.


Not scheduled. Each follows the registry pattern (one directory with descriptor, input, optional view and editor extras, one import line in `index.ts`). Check `fromSchema` precedence for each one.

| Type | Stored as | Notes |
|---|---|---|
| Partial date | string, pattern `YYYY`, `YYYY-MM` or `YYYY-MM-DD` | For "1973" or "Mar 1973" when the day is unknown. Current Date needs a full date. Also suits the planned GEDCOM import (partial dates). Register before `text`. |
| Money | number (+ optional currency code in the schema) | Two-decimal handling, currency shown in view. For purchase price and value. |
| URL / Email / Phone | string with `format: uri` / `email` and a pattern for phone | Cheap. URL is already sketched in `docs/field-types.md`. Depends on WI-4 so `format` strings are recognised. |
| Multi-choice | array of strings with `items.enum` | Tick several options. **Collision:** `group.fromSchema` currently matches any `type: 'array'`. Register multi-choice before group, and make group require `items.type === 'object'` (WI-4). |
| Identifier | string with `pattern` | ISBN, catalogue number, barcode. Builds on the WI-15 pattern and friendly-error machinery. Later a hook for enrichment lookups (TMDB, MusicBrainz, books). |
| Duration | number of seconds, or string | Entered as `mm:ss` / `h:mm:ss`. Track and film lengths. |
| Measurement | number with a unit stored in the schema | Dimensions, weight. |
| Location | object `{label, lat?, lng?}` | One-off places on any item type ("Purchased at"); a connection to a Place item is better when the place has its own details or there are several. See the details below. |
| Condition / grade (Mint, NM, VG+…) | Choice | Not a new type. Ship ready-made option lists (built-in choice lists, WI-19c) that can be picked when creating a Choice field. |
| Country | Choice | Koillection has a Country field. Not a new type: a built-in "Countries" choice list (WI-19c). |
| Image / File | reference to a media asset | Koillection has both. The media module only supports a closed `AttachmentKey` enum with the single value `cover`, so per-field images would need that to accept field keys, and archive/purge (WI-8, WI-9) would need to cover attachments. Needs its own design. |

Not proposed: a "link to another item" field. Edges already model that.

## Location kind (candidate, any item type)

A `location` kind for one-off places on **any** item type (for example "Purchased at", "Photographed at", "Stored in"), not only on Place items. Add it when a concrete collection needs it (guidelines §16a). Users also get a rule of thumb, shown next to the kind in the editor: use a **location field** for a simple label or coordinates on a single item; use a **connection to a Place item** when the place has its own details, appears on several items, or the item has several (a poster signed in London, Liverpool and Southampton is three connections, each with its own date and signer).

**Stored as** a small object; verified that `@cfworker/json-schema` and Python `jsonschema` agree on it, including `dependentRequired`:

```json
"purchased_at": {
  "title": "Purchased at",
  "type": "object",
  "properties": {
    "label": { "type": "string" },
    "lat": { "type": "number", "minimum": -90, "maximum": 90 },
    "lng": { "type": "number", "minimum": -180, "maximum": 180 }
  },
  "dependentRequired": { "lat": ["lng"], "lng": ["lat"] },
  "x-menagerist": { "kind": "location" }
}
```

A value is `{"label": "Camden Market"}`, or with coordinates `{"label": "Camden Market", "lat": 51.541, "lng": -0.146}`. Either part is optional, coordinates come as a pair, and an empty object is valid, so the editor must omit an empty location instead of saving `{}` (the WI-1 rule).

**In the app**
- **Entering:** a text box for the label, an optional "Add coordinates" disclosure (two numbers, or paste `51.541, -0.146`), and a "Use my current location" button. The browser only allows that over HTTPS or on localhost, so hide the button when it is unavailable (a self-hoster on a plain LAN address will not see it).
- **Viewing:** the label, with an "Open in map" link when coordinates exist. No embedded map, no tiles, no address lookup and no mapping library; the link is an ordinary external navigation to OpenStreetMap (decided; a `geo:` link can be added later).
- **Cards and highlights:** highlightable (WI-16); the compact view shows the label, or the coordinates when there is no label.
- **Search:** the label is found by WI-17 (strings inside objects are scanned). Coordinates are numbers, so a search for "51" can match a latitude; accepted for v1 (decided).
- **Not a group sub-field** in v1 (`canBeSubField: false`).

**Prerequisite:** the attributes editor's rows only hold text or table rows, and `attributesToRows` runs `String(value)` on everything, so an object value becomes `"[object Object]"`. This kind needs the same lossless-value round-trip as WI-18a: give `AttributeRow` a value type that can carry an object, and have the editor and `rowsToAttributes` pass it through untouched.

**Backend:** nothing new; plain JSON in the existing column, no port. Privacy note: coordinates of a storage location can reveal a home address, so any future sharing or export feature must treat them as sensitive.

**Deferred:** map tiles and address lookup (an external service, tile and content-security-policy configuration, and a mapping library), and "near me" search (PostGIS or similar, which is a lot of ceremony).
