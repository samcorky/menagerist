# WI-21: Value suggestions, turn repeated text into connections or choices

> Part of the field-types spec. Read `00-INDEX.md` and `01-context-and-conventions.md` first (skip the second if this is that file).
> **Depends on:** WI-18c (custom names), WI-10 (text to choice), WI-14 (`suggest` member). Later.
> "WI-n" refers to `wi-*.md` files listed in `00-INDEX.md`; "open question N" refers to `open-questions.md`.


**Verdict.** A good idea, as long as it only ever *suggests*. It matches the roadmap's journey ("start simple, add things, discover relationships, unlock the full graph"): a user types "Miles Davis" as an Artist on three records, and the app notices and offers to make him an item those records link to. The same detector also handles the "Film" case, but the right suggestion depends on how the values are distributed, so it produces one of two outcomes.

**Two outcomes from one detector.**
1. **Entity-like values** (many different values, each repeated a few times: "Miles Davis", "Back to the Future"): suggest **linking** to an item through an edge. Lead with an existing match ("You already have an item called Miles Davis (Person). Link these 3 records to it?"); otherwise offer to create the item.
2. **Category-like values** (few different values repeated many times: "LP" and "CD", or a "Film" value in a Format field): suggest **turning the field into a Choice** with those values as options (and optionally saving the list as a preset, WI-19). Linking would be wrong here.

The user always confirms; nothing runs automatically.

**Links are edges, not a new field kind.** The spec still does not add a "link to another item" field; edges already carry direction, labels and attributes, and feed the Explore graph. Verified in the graph module: an `Edge` has `source_id`, `target_id`, `type` and attributes and cannot connect a node to itself; edge types are a controlled vocabulary with `label`, optional `reverse_label` and `directional`; `CreateEdge` auto-creates an unknown edge type from the slug ("the vocabulary builds itself"); `Node.type` is optional, so a new target item can be left untyped; and there is no uniqueness constraint on (source, target, type), so the link command must check for existing edges itself.

## Detector (backend query, on demand only)

- Runs for one item type and one text field (or custom detail name from WI-18c) at a time, when the user opens the schema editor or an item. Never in the list or search path, and no background job.
- Only `text` fields (and custom details holding strings). Ignore empty values, non-strings, choice, longtext and every other kind. Skip values longer than a short limit (proposal: 60 characters) and values that look numeric or like dates.
- **Normalise** by lowercasing, trimming and collapsing whitespace. Exact-normalised matches only in v1; fuzzy variants ("Miles Davis Quintet", "Davis, Miles") are a later review UI. Multi-valued cells ("A; B", "A & B") are not split in v1.
- **Classify** with tunable constants (proposal, to be adjusted on real data): *link* when a value repeats at least 3 times and the field has many distinct values (for example 8 or more); *choice* when the field has few distinct values (for example 12 or fewer) and many filled items (for example 10 or more).
- **Match existing items** by normalised name across all item types, and return them with the cluster.
- Verified on PostgreSQL 16: grouping by `lower(regexp_replace(btrim(attributes->>:key), '\s+', ' ', 'g'))` merged "Miles Davis" and "miles  davis " into one cluster of 3, skipped empty and numeric values, showed a few-distinct-values field as a choice candidate (LP 6, CD 1), and a normalised-name lookup found the existing Person "Miles Davis". Diacritic folding can happen in Python after the query (no `unaccent` extension needed).

## Actions

- **Connect.** Choose or create the item to connect to (with an optional item type; untyped is allowed), choose how they are connected (a plain-language label, default the field's label, for example "Artist"; internally the slug becomes an edge type, an unknown slug is created automatically, and a reverse label can be set), and tick which items to connect (all ticked by default, shown as a list). The command creates the connections, skips any that already exist, and reports created and skipped. The result appears as "3 items connected" with the 5-second Undo toast (guidelines §14) rather than a confirmation.
- **Keep the text (v1).** The attribute values are **not** cleared, so the whole action is reversible by deleting the edges and nothing drifts silently. When every filled item is linked, offer "Hide the 'Artist' field?", which archives it (WI-8). A later version can show linked items where the field was (for example a highlight that shows an edge type on cards, WI-16 follow-up).
- **Turn into a choice.** A client-side schema edit (`PATCH /node-type/{id}`): the field's kind changes from text to choice with the distinct stored values as options. This is the one safe text-to-choice conversion, because the options are built from the existing values, so every stored value is valid at that moment. WI-10's compatibility table allows it *only* through this suggestion. Values differing only in case or spacing become separate options; tidying them is a manual edit for now.

## Where suggestions appear (progressive disclosure)

- The schema editor's passive "Tips" strip in Settings, shared with the WI-18c custom-name tips.
- ~~A quiet inline hint on an item under the field~~ **Removed from v1.** It would surface a suggestion while the user is just browsing or editing, which guidelines §16b says the app should not do. Revisit only if that section is amended (open question 44).
- **Prevention (WI-21a, cheap and independent):** type-ahead on text fields that offers previously used values and matching items ("Miles Davis (Person)"). Choosing an item creates an edge instead of free text, and picking a previous value avoids new variants.
- **Guardrails: two ways to say no.**
  - **"Never suggest for this field"** is permanent and shared. It is stored in the item type's schema on that property, applies on every device and for every user of that item type, and affects only that field:

    ```json
    "artist": {
      "title": "Artist",
      "type": "string",
      "x-menagerist": { "kind": "text", "suggest": false }
    }
    ```

    It is switched back on with a "Suggestions" toggle under the field's Advanced section in the schema editor.
  - **"Not now"** is temporary and per browser. It is stored in `localStorage` under a single key (proposal: `menagerist:suggestions:dismissed`), grouped by item type slug, then field key, then normalised value, together with the count at the time of dismissal:

    ```json
    {
      "record": {
        "artist": {
          "miles davis": { "count": 3, "at": "2026-09-21" }
        }
      }
    }
    ```

    - Dismissing one value hides only that suggestion; other values on the same field ("John Coltrane") can still appear.
    - **Reappearance rule (proposal):** a dismissed suggestion returns only when its count has at least doubled since the dismissal (for example 3 becomes 6), so it does not nag but is not lost forever.
    - It is not synced between devices, which is why the permanent choice lives in the schema.
    - Reads and writes are wrapped in `try/catch` (as elsewhere in this spec); if storage is empty or blocked, the suggestion simply shows again.
  - A global off switch in settings is an open question.

## Backend surface (proposal, matching the existing router style)

| Item | Kind | Notes |
|---|---|---|
| `ListAttributeValues` | query | Distinct values with counts, filtered by `q`, for the type-ahead. `GET /node-type/{node_type_id}/attribute/{key}/values` (`list_attribute_values`). |
| `ListAttributeValueSuggestions` | query | Clusters with counts, sample node ids, existing-item matches, and the classification (link or choice). `GET /node-type/{node_type_id}/attribute/{key}/suggestions` (`list_attribute_value_suggestions`). |
| `LinkAttributeValueToNode` | command | Atomically (one unit of work): create the target item if needed, create the edges (auto-creating the edge type), skip duplicates, return `{target_id, created, skipped}`. `POST /node-type/{node_type_id}/attribute/{key}/link` (`link_attribute_value_to_node`), body `{value, node_ids, target: {node_id} or {new_node: {name, type?}}, edge_type}`. |

The choice conversion needs no backend command. Authorisation follows the WI-9 decision (open question 17). Reads use only the existing `nodes` and `edges` tables; no migration.

## Interactions

- WI-18: custom details are clustered too (the detector accepts any top-level key), and adopting a custom detail into a field (WI-18c) and linking it are separate, compatible actions.
- WI-16: highlights stay per type; showing linked items on cards is a follow-up that would let a highlight point at an edge type.
- WI-17: search still finds the text values; the new linked item is reachable as an ordinary item.
- WI-19: a choice suggestion can offer "Save the list as a preset".
- WI-20: readable keys make the suggestion text natural ("Artist" rather than an id).
- The target item's own fields are ordinary schema fields; nothing new is needed.

**Acceptance.**
- Three records with "Miles Davis" (one typed "miles  davis ") in Artist, and an existing Person "Miles Davis", produce a link suggestion that names the existing item. Confirming creates three edges and leaves the text values in place; running it again creates none.
- A Format field with values LP (many) and CD (few) produces a choice suggestion, not a link suggestion; confirming converts the field and every item stays valid.
- Dismissing with "Never suggest for this field" stops suggestions for that field for good.
- Nothing is computed while listing or searching items.

**Tests.**
- Unit: normalisation and grouping; classification thresholds; exclusions (empty, numeric, long, non-text kinds); existing-item matching.
- The link command against the in-memory repositories: creates the target item, creates edges, skips duplicates, refuses a self link, and is idempotent on a second run.
- Integration `I-10` (real Postgres): the clustering and name-match queries as verified above, scoped to one item type and excluding soft-deleted nodes; the whole link transaction rolls back if any edge fails.
- Frontend: strip and inline hint rendering; "Not now" storage (write, hide, reappear when the count doubles, survive missing or blocked `localStorage`); per-field opt-out through `x-menagerist.suggest: false`, including switching it back on.
- End-to-end: see the suggestion, link three records, and see the edge on each record's page.
