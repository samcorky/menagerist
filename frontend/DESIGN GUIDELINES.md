# Menagerist Frontend Design Guidelines

**Status:** Living document — governs all UI/UX decisions for the Menagerist frontend.
**Audience:** Human contributors and AI coding agents working on the SvelteKit frontend.
**Scope:** Product/UX rules only. For code architecture, state management, and component internals, see the engineering docs.

---

## 1. Purpose

Menagerist is a personal collection and knowledge-management application. The data model underneath is a generic graph (nodes and edges) — but **the user must never see or need to understand that**.

The frontend's job: make managing a collection feel simple, approachable, and enjoyable, no matter how sophisticated the underlying model gets.

> **The Golden Rule:** Menagerist must be powerful enough for a power user while remaining completely approachable to someone who has never used a collection-management app before. Users should be able to _discover_ complexity when they want it. They should never be _forced_ to understand it.

---

## 2. Design System (binding)

| Layer                | Choice        |
| -------------------- | ------------- |
| Component library    | shadcn-svelte |
| Styling              | Tailwind CSS  |
| Icons                | Lucide        |
| shadcn-svelte preset | `bK0zvfkNE`   |

**Rules:**

- Reuse existing components and established shadcn-svelte patterns before building bespoke UI.
- Do not introduce new colors, spacing scales, or component styles that compete with the preset.
- If a pattern doesn't exist yet, check whether an existing component can be composed to solve the problem before creating a new one.

---

## 3. Core Principles

### 3.1 Dummy-friendly by default

Assume the user is not technical. Never require them to understand databases, schemas, entities, relationships, graph structures, metadata models, queries, or filters. Use plain, human language everywhere.

| Don't say                    | Say instead                                   |
| ---------------------------- | --------------------------------------------- |
| `Items where signed = true`  | Signed items                                  |
| `Person relationship: actor` | Connected to Keanu Reeves                     |
| Node / Entity                | Item, Person, Place (whatever it actually is) |
| Edge                         | Connection                                    |

The data model can be sophisticated. The interface cannot.

### 3.2 Collection first

The user's collection is the star of the app. Menagerist should feel like a beautiful, organised collection — not an admin panel. Images, titles, and identifying info get visual priority over metadata and controls.

### 3.3 Progressive disclosure

Show the simplest useful interface first. A first-time user must be able to do all of the following with zero configuration:

1. Open Menagerist
2. Add an item
3. Find an item
4. View an item
5. Edit an item

Advanced functionality exists, but is discovered, not front-loaded.

### 3.4 Minimise decisions

Don't ask the user something Menagerist can reasonably infer or default. Prefer automatic detection, suggestions, and sensible defaults over up-front configuration.

- **Don't:** Entity → Type → Collection → Schema → Metadata template
- **Do:** Add item (then infer/ask only what's needed, when needed)

### 3.5 One obvious action per screen

Every screen has a single clear primary action. Avoid multiple equally-weighted primary actions.

| Screen            | Primary action         |
| ----------------- | ---------------------- |
| Collection        | Add item               |
| Empty collection  | Add your first item    |
| Search            | Search your collection |
| Item detail       | Edit                   |
| Item missing info | Add information        |

### 3.6 First-run experience

A brand-new user opening Menagerist for the first time sees an empty collection. This is a specific scenario with specific needs — it is not the same as the empty state after a failed search.

**Rules:**

- Do not show a setup wizard, onboarding tour, or modal that must be dismissed before the user can act. These create friction before the user has experienced any value.
- The empty collection state is the onboarding. It must be warm, direct, and immediately actionable — one clear CTA ("Add your first item") is sufficient.
- Do not ask the user to configure anything before they add their first item. Category setup, schema definition, and collection settings are all discoverable after the fact.
- If the app has been used before (items exist or were recently deleted), do not show the first-run empty state — show the standard empty state (§11) instead.

---

## 4. Mobile First

Mobile is not a cut-down desktop experience — design for touch from the start.

**Mobile priorities:**

- Large, comfortable touch targets (generous hit area even if the visual control is compact)
- Clear visual hierarchy
- Minimal navigation chrome
- Short forms, minimal typing
- Bottom sheets for contextual actions
- Full-screen search where appropriate
- Responsive image grids
- No horizontal scrolling for normal content

---

## 5. Responsive Layout

### Desktop

Persistent sidebar where appropriate.

```
┌──────────────┬─────────────────────────────┐
│              │                             │
│ Collection   │ Collection                  │
│ Timeline     │                             │
│ Explore      │       Items                 │
│              │                             │
│ + Add item   │                             │
│              │                             │
└──────────────┴─────────────────────────────┘
```

### Tablet

Sidebar collapses to an icon rail or is hidden behind a toggle. Content takes priority over chrome. Navigation tabs move to the top or into a slide-out drawer — do not attempt to reproduce the full desktop sidebar.

```
┌─────────────────────────────────────────┐
│ ≡  Menagerist                    🔍  ⋮  │
├─────────────────────────────────────────┤
│                                         │
│  ┌──────┐  ┌──────┐  ┌──────┐           │
│  │ IMG  │  │ IMG  │  │ IMG  │           │
│  └──────┘  └──────┘  └──────┘           │
│                                         │
│  ┌──────┐  ┌──────┐  ┌──────┐           │
│  │ IMG  │  │ IMG  │  │ IMG  │           │
│  └──────┘  └──────┘  └──────┘           │
│                                         │
└─────────────────────────────────────────┘
```

### Mobile

Compact header + bottom navigation. **Do not** attempt to reproduce the desktop sidebar at small widths — redesign the layout for the viewport rather than shrinking it.

```
┌─────────────────────────────┐
│ Menagerist          🔍  ⋮   │
├─────────────────────────────┤
│                             │
│ Collection                  │
│                             │
│  ┌──────┐  ┌──────┐         │
│  │ IMG  │  │ IMG  │         │
│  └──────┘  └──────┘         │
│                             │
├─────────────────────────────┤
│ Collection  Search  Explore │
└─────────────────────────────┘
```

---

## 6. Navigation

Keep navigation small. Core destinations:

- **Collection**
- **Search**
- **Explore**

Rules:

- "Add item" must always be easy to find, on every breakpoint.
- Settings must not compete visually with the primary collection experience.
- Do not add nav items for features used only occasionally — surface those contextually instead.

---

## 7. Collection View

The collection is the primary application view. It must support:

- Grid view
- List view
- Search
- Filtering
- Sorting
- Infinite scrolling
- Responsive layouts

**Defaults:** Favour visual browsing (grid) as the default view.

**Cards:** Show only what's needed to identify an item. Avoid excessive badges, metadata, buttons, or decoration.

### 7a. Filtering

Filters must never look or feel like queries. The user selects from what exists in their collection — they never write expressions.

**Interaction model:**

- Filters are presented as filter chips or a filter panel, not a query builder.
- Available filter values are surfaced from the user's actual data (e.g. showing only formats that appear in the collection, not every possible format).
- Multiple active filters combine with AND logic — the UI should make this obvious without using the word "AND."
- Active filters are always visible and easy to clear individually or all at once.

**Plain-language filter examples:**

| Filter concept                  | UI label              |
| ------------------------------- | --------------------- |
| `signed = true`                 | Signed                |
| `format = "Blu-ray"`            | Format: Blu-ray       |
| `year >= 1990 AND year <= 1999` | From the 1990s        |
| `connections.type = "Actor"`    | Connected to an Actor |

Filters that return zero results should tell the user why and offer to clear the relevant filter — never show a silent empty state.

### 7b. Image Handling

Images are central to the collection experience and must be handled consistently across all views.

**Aspect ratio:**

- Cards use a consistent aspect ratio within a given collection view — do not mix portrait, landscape, and square cards in the same grid.
- The default card ratio is 2:3 (portrait) — appropriate for most physical media. Category types may define their own preferred ratio (e.g. 16:9 for film posters, 1:1 for vinyl). When a ratio is not defined, use the default.

**Placeholders:**

- Every item without an image shows a placeholder that fills the same space as an image would — never collapse the card or shift layout for missing images.
- Placeholders use a muted background with a centered icon representing the item's category (e.g. a film reel for films, a disc for music). If no category icon exists, use a generic item icon.
- Placeholders must be visually consistent between light and dark themes (§21a).

**Loading:**

- Images load lazily — do not block card render on image load.
- While an image is loading, show the placeholder. Transition to the loaded image with a short fade (150 ms, or instant if `prefers-reduced-motion` is set).

**Broken images:**

- If an image URL fails to load, fall back to the placeholder silently — do not show a broken image icon or an error.

### 7c. Truncation Rules

Long content must truncate consistently. These rules apply across cards, list rows, and any context where space is constrained.

| Content                          | Truncation rule                                                             |
| -------------------------------- | --------------------------------------------------------------------------- |
| Item title (card)                | Single line, ellipsis at end                                                |
| Item title (list row)            | Single line, ellipsis at end                                                |
| Item title (detail view)         | No truncation — wrap fully                                                  |
| Subtitle / secondary info (card) | Single line, ellipsis at end                                                |
| Description / long text (card)   | Do not show — omit entirely                                                 |
| Description / long text (detail) | Show in full, or collapsed with "Show more" if > ~5 lines                   |
| Tag / chip labels                | Truncate at a fixed max width with ellipsis; show full label on hover/focus |
| Connection labels                | Single line, ellipsis at end                                                |

**Rules:**

- Never truncate in the middle of a word — always break at a word boundary before the ellipsis.
- Truncated content must be accessible in full on hover (tooltip) on desktop and on tap/long-press on mobile, or visible in the detail view.
- Do not truncate item titles in the detail view under any circumstances — the detail view is where the user reads, not scans.

### 7d. Bulk Actions

Users may need to act on multiple items at once (delete, tag, move to a category). Bulk actions are an advanced operation and must not clutter the default collection view.

**Activation:**

- Bulk selection is entered explicitly — via a "Select" button, a long-press on mobile, or checkbox reveal on desktop hover. It is never the default interaction mode.
- Entering bulk selection mode should be clearly signalled (e.g. checkboxes appear on cards, a selection bar appears at the top or bottom of the screen).

**While selecting:**

- Show a count of selected items ("3 selected").
- Provide a "Select all" option.
- Provide a clear way to exit selection mode without taking an action.

**Available bulk actions** (minimum set):

- Delete selected
- Add tag to selected
- Remove from collection / move to category _(when applicable)_

**Rules:**

- Bulk delete follows the same undo pattern as single-item delete (§14) — "X items deleted → Undo."
- Bulk actions must not be destructive without confirmation or an undo escape (§14).
- On mobile, bulk action controls live in a bottom action bar — never in a dropdown that requires precision tapping.

---

## 8. Search

Search must be fast, forgiving, and usable with natural language — never a query syntax the user has to learn.

Example queries that must work:

```
matrix
signed items
things from 1999
keanu reeves
recently added
```

**Result grouping:** Distinguish result kinds where useful (Items, People, Collections, Tags, other relevant entities) — but label them in plain language, not by their internal type.

Search should remain useful even when the user doesn't know exactly what they're looking for (i.e., it should degrade gracefully to browsable/fuzzy results, not "no results found").

---

## 9. Adding Items

Never open with a large form. Start minimal:

```
What are you adding?

[ Item name                         ]

[ Continue ]
```

Where possible, the system should do work on the user's behalf:

- Detect item type
- Suggest metadata
- Look up existing information (enrichment)
- Apply sensible defaults
- Avoid asking for duplicate information
- Let the user skip anything optional

### 9a. Item Type Detection

Detection is based on the name string entered by the user. It is best-effort — never a hard gate.

**Rules:**

- If a type is detected with reasonable confidence, apply it silently and show it as a pre-filled field the user can change. Do not ask the user to confirm before proceeding.
- If confidence is low or ambiguous, show the most likely suggestion and let the user correct it inline — don't delay the flow to ask.
- If no type can be inferred, default to a generic item type and proceed. Never block the add flow on detection failure.
- Detection results must be presented using plain-language category names (§24), not internal type identifiers.

**Rule: incomplete data is always better than blocking the save.** Never prevent a user from adding an item because a field is empty, unless that field is truly required for the record to exist (e.g., a name).

---

## 10. Editing Items

Editing should feel like editing an object, not editing a database row.

- Show important information first.
- Group advanced/rarely-used fields into expandable sections.
- Never present a wall of empty fields.

Example:

```
The Matrix

Film · 1999

Overview

Condition
Excellent

Format
Blu-ray

More information
› Identification
› Purchase information
› Additional details
```

---

## 11. Empty States

Empty states must always answer: **"What should I do now?"**

| Quality | Example                                                                                   |
| ------- | ----------------------------------------------------------------------------------------- |
| Bad     | No items found.                                                                           |
| Better  | Your collection is empty.                                                                 |
| Best    | Your collection is empty. Add your first item to get started. `[ + Add your first item ]` |

---

## 12. Errors

Never expose raw technical errors to the user.

| Don't                       | Do                                                                               |
| --------------------------- | -------------------------------------------------------------------------------- |
| `HTTP 422: ValidationError` | **We couldn't save this item.** Check the highlighted information and try again. |

Provide a clear recovery action whenever possible.

### 12a. Network & Offline States

Connectivity failures are distinct from validation errors and must be handled separately.

**Rules:**

- Offline support is not a goal — Menagerist requires a network connection to function. Do not attempt to queue writes or sync offline changes.
- When a request fails due to a network error (timeout, connection refused, no internet), show a user-readable message with a retry action. Never show a raw network error or status code.
- Distinguish between "you're offline" and "something went wrong on our end" where detectable:
  - No connectivity: "You appear to be offline. Check your connection and try again."
  - Server/unknown error: "Something went wrong. Try again, or reload the page if the problem persists."
- Do not block the entire UI on a network failure for read operations — show cached/stale content where available and indicate it may be out of date. For write operations, surface the error inline at the point of action.
- Background operations (e.g. enrichment lookups) that fail should fail silently with a graceful fallback (e.g. no suggestions surfaced) — do not interrupt the user's flow for a non-critical background failure.

---

## 13. Feedback

Every meaningful action gets clear, lightweight feedback — do not interrupt with unnecessary modal dialogs for routine confirmations.

**Toast vs. inline:**

| Use a toast when…                                                  | Use inline feedback when…                                                   |
| ------------------------------------------------------------------ | --------------------------------------------------------------------------- |
| The action completed in the background or outside the current view | The result is visible in the current view (e.g. a field saved, a tag added) |
| The feedback includes an Undo action (§14)                         | The feedback is an error or warning tied to a specific field or element     |
| The user navigated away before it resolved                         | The state change is permanent until the user changes it again               |

Examples: "Item saved," "Item deleted — Undo," "Changes saved."

### 13a. Loading States

Every operation that takes time needs a loading state. Inconsistent or missing loading states erode trust.

**Threshold rule:** Do not show a loading indicator for operations expected to complete in under 300 ms. Show one for anything that may take longer. This avoids flickering loaders for fast responses while ensuring the user always gets feedback on slow ones.

**Skeleton screens vs. spinners:**

| Use skeletons when…                                                                                    | Use a spinner when…                                                                                       |
| ------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------- |
| The layout of the content is known in advance (e.g. a card grid, a list of items, an item detail page) | The layout or size of the content is unknown (e.g. a modal about to open, a search with variable results) |
| Initial page/view load                                                                                 | An in-place action is in progress (e.g. saving, submitting)                                               |

**Rules:**

- Skeletons must match the approximate shape and density of the real content — a skeleton that bears no resemblance to what loads is worse than a spinner.
- Never show both a skeleton and a spinner simultaneously.
- Inline actions (save, delete, tag) show a spinner on the triggering control, not a full-page loader.
- A full-page loader is only appropriate for hard navigations where no partial content can be shown. Avoid it everywhere else.
- Loading states respect `prefers-reduced-motion` — reduce or remove skeleton shimmer animations; the skeleton shape itself still appears.

---

## 14. Confirmation vs. Undo

**Do not** ask for confirmation on harmless or easily-reversible actions.

**Do** ask for confirmation only when an action is destructive, hard to undo, or genuinely surprising.

Prefer Undo over a confirmation dialog wherever the action can be reversed:

- **Preferred:** `Item deleted` → **Undo**
- **Avoid:** "Are you sure you want to delete this item?" + a second click

**Undo timeout:** The undo toast persists for **5 seconds** before the action is committed. This is the standard window across the app — do not use different durations in different places. The deletion (or other destructive action) is deferred on the server until the timeout elapses or the user navigates away, whichever comes first. If the user navigates away before 5 seconds, the action commits immediately.

If an action cannot be undone (e.g. permanent deletion of a category with many items), do not use the undo pattern — use a confirmation dialog instead, and explain clearly what will be lost.

---

## 15. Forms

- Clear labels, always.
- Minimise required fields.
- Explain any field whose purpose isn't obvious.
- Sensible defaults everywhere possible.
- Preserve entered data across validation errors — never make the user retype.
- Validate at useful moments (not eagerly on every keystroke).
- Validation copy should read as helpful guidance, not a programmer's warning.

---

## 16. Metadata Presentation

Metadata is presented as **information**, never as implementation detail.

- **Do:** `Year` / `1999`
- **Don't:** expose internal field identifiers, database types, or backend schema structure (foreign keys, enum codes, UUIDs).

Optional information stays optional. Users enrich items progressively over time — the UI must support partial records gracefully at every stage, not just at creation.

**Categories (item types) and relationship types may optionally define a schema** — a small set of fields (a name, a kind, and whether it's required) that every item of that type is expected to have. This is a real, user-authored structure, not a backend implementation detail, so defining and seeing it is not "schema exposure" in the §16 sense — what's forbidden is exposing _how_ it's implemented (raw type enum values, internal field IDs), not the concept of "this category has some suggested fields."

A category is not required to define one. **Types with no schema behave as fully freeform** — nothing changes for them, and this is expected to be the common case for anything the user hasn't bothered to formalise.

### 16a. Category & Relationship-Type Schemas

Schemas are defined once, per category or relationship type, from **Settings → Categories / Relationships** — not per item. An item of that type then shows those fields prominently, with anything else the user adds appearing as separate custom fields underneath.

**Defining a schema field (in Settings):**

1. **Label** — free text (e.g. "Rating," "Pressing," "Signed by"). This is the only name the user provides; don't also ask for a separate internal "key" — derive it the same way category slugs are already derived elsewhere in the app (auto-slugify the label, don't surface the slug as a thing to fill in).
2. **Kind** — a plain-language picker of how the value should be entered/displayed (table below). Present these as ordinary words ("Number," "Yes/No," "Rating"), not as raw type strings or abbreviations — the current implementation's dropdown (`text` / `number` / `boolean` / `date` / `select` / `richtext`) and "Req" checkbox label need updating to match this.
3. **Required** _(optional toggle)_ — marks the field as expected for that category. See the required-fields rule below before treating this as a hard constraint.

**Field kinds:**

| Kind      | Entry widget                         | Notes                                                                          |
| --------- | ------------------------------------ | ------------------------------------------------------------------------------ |
| Text      | Single-line input                    |                                                                                |
| Long text | Multi-line input                     | maps to current `richtext`                                                     |
| Number    | Numeric input                        |                                                                                |
| Yes/No    | Toggle switch                        | maps to current `boolean` — not a checkbox labelled "Req"-style                |
| Choice    | Dropdown or radio buttons            | maps to current `select`; needs a defined option list                          |
| Date      | Date picker                          |                                                                                |
| Rating    | Stars, numeric (e.g. /10), or slider | not yet in the shipped kind set — add when a concrete collection type needs it |

This is the same kind set and widgets whether the field comes from a category schema or is added freeform on an individual item (§16b) — one mental model for "what kind of field is this," used in both places.

**Required fields are a soft signal, not a hard block.** A missing required field should be visually flagged (e.g. highlighted, or counted in an "items missing information" smart group per §18) but must never prevent saving. This keeps §9's "incomplete data is always better than blocking the save" rule intact even though "required" now exists as a real, user-set flag — required expresses _the collector's_ intent for what a complete record looks like, not a validation constraint the app enforces on their behalf.

### 16b. Freeform Custom Fields

On any item, regardless of whether its category has a schema, the user can add additional fields beyond the schema — or, for unschemaed types, any fields at all. These use the same Name + Kind flow as §16a, entered directly on the item rather than in Settings, and are not added to the category's schema automatically. If the same field name recurs across several items of a type, that's a signal the category could use a schema field for it (§16a) — but Menagerist doesn't do this automatically or nag the user to formalise it; it's a manual step the user takes in Settings if and when they want it.

---

## 17. Relationships & Connections

Relationships are a powerful feature but must stay understandable. Always render them as natural language, never as graph terminology.

```
Connected to

Keanu Reeves
Actor

Science Fiction
Genre

The Matrix Reloaded
Related item
```

**Rule:** Graph terminology (node, edge, graph) must never appear in standard UI. It may only appear if/when the user explicitly enters an advanced "Explore" experience built for that purpose — and even there, prefer softened language ("Connections map" over "graph view") unless power users have asked for the technical framing.

The graph is something the user _experiences_, never something they need to _understand_.

---

## 18. Smart Groups

Surface useful groups automatically — never require the user to build these manually:

- Recently added
- Favourites
- Signed items
- Items missing information
- Items from the 1990s
- Most connected
- Recently viewed

These should feel helpful, not magical or confusing — if a group's membership isn't obvious from its name, add a one-line explanation.

### 18a. Freshness Definitions

"Recent" is not ambiguous — use these thresholds consistently across the app:

| Group           | Window                        |
| --------------- | ----------------------------- |
| Recently added  | Added within the last 30 days |
| Recently viewed | Viewed within the last 7 days |

If a smart group's membership window is surfaced in the UI (e.g. as a subtitle or tooltip), express it in plain language: "Added in the last 30 days," not "created_at > now() - interval '30 days'."

These windows may be made configurable per user in future, but are fixed defaults until then. Do not hard-code different values in different parts of the app.

---

## 19. Infinite Scrolling & State Preservation

Large collections use incremental loading. When a user navigates from the collection into an item and back **within the same session and tab**, preserve exactly:

- Scroll position
- Active filters
- Active sort
- Active search query
- View mode (grid/list)

The user returns to exactly where they left off.

**Edge cases:**

- **Direct link / deep link entry:** If the user arrives at an item via a direct URL (bookmarked, shared, or opened in a new tab), there is no collection context to restore. On back-navigation, load the collection at its default state rather than attempting to reconstruct a session that doesn't exist.
- **Multiple tabs:** State is not shared across tabs. Each tab maintains its own independent collection state.
- **Session expiry / page reload:** State does not need to survive a hard reload. Persisting it across reloads is a nice-to-have, not a requirement.

---

## 20. Accessibility

Not optional. Every screen must provide:

- Full keyboard navigation
- Visible focus states
- Semantic HTML
- Accessible labels (aria-*, alt text, etc.)
- WCAG-appropriate colour contrast
- Screen-reader-friendly controls
- Touch-friendly controls (see §4)
- `prefers-reduced-motion` support

**Rule:** Never communicate important information through colour alone (pair with icon, label, or text).

### 20a. Focus Management

"Full keyboard navigation" means focus is managed deliberately after every action — not just that interactive elements are reachable via Tab.

| Action                                               | Focus moves to…                                                                                                           |
| ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| Dialog / sheet opens                                 | First focusable element inside the dialog                                                                                 |
| Dialog / sheet closes                                | The element that triggered it                                                                                             |
| Item deleted from a list                             | The next item in the list; if none, the previous item; if the list is now empty, the list container or the primary action |
| Toast appears                                        | Toast does not receive focus — it is announced to screen readers via `aria-live`                                          |
| Form submits successfully and stays on the same page | The confirmation message or the first field if the form resets                                                            |
| Inline edit confirmed                                | The display value that replaced the input                                                                                 |
| Bulk selection entered                               | The first selectable item                                                                                                 |
| Bulk selection exited                                | The "Select" control that triggered selection mode                                                                        |

**Rules:**

- Focus must never be lost to `<body>` or an invisible element after an action.
- Dialogs and bottom sheets must trap focus while open — Tab cycles within them, not to the content behind.
- Modals that close on Escape must return focus to the trigger.
- Do not move focus automatically for non-modal UI updates (toasts, inline feedback, count badges) — only move focus when the user has explicitly triggered a transition.

---

## 21. Visual Design

**Aim for:** calm, clean, modern, compact, content-focused, consistent.

**Avoid:**

- Excessive gradients, shadows, or decorative animation
- Oversized headings or buttons
- Excessive cards or badges
- Arbitrary/off-system colours
- Dense walls of metadata

The collection's own content (images, titles) should provide most of the visual interest — the chrome should stay quiet.

### 21a. Dark Mode

The shadcn-svelte preset ships with both light and dark themes. Both must be supported.

**Rules:**

- All colour contrast requirements (§20) apply to both themes independently — verify WCAG compliance in each.
- The "colour is never the sole carrier of meaning" rule (§20) applies in both themes — do not rely on a colour that reads clearly in light mode but becomes ambiguous in dark.
- Do not hard-code colour values outside the design system token set. Use semantic tokens so light/dark switching is automatic.
- Images and user-uploaded content are not theme-aware — ensure the card/container treatment works acceptably against both background colours.
- The theme follows the user's system preference by default (`prefers-color-scheme`). A manual override toggle may be added as a Settings option but is not required initially.

---

## 22. Animation

Use short, subtle transitions to communicate state and hierarchy — not for decoration. Appropriate uses: opening dialogs, expanding sections, navigation transitions, loading states, adding/removing content.

Avoid animation that slows down repeat/experienced users. Always respect `prefers-reduced-motion`.

**Timing guidelines:**

| Transition type                                   | Duration   |
| ------------------------------------------------- | ---------- |
| State changes (toggle, checkbox, badge)           | 100–150 ms |
| Element enter/exit (toast, chip, inline feedback) | 150–200 ms |
| Panel/sheet open/close                            | 200–250 ms |
| Page/route transitions                            | 250–300 ms |

When `prefers-reduced-motion` is set, reduce all transitions to ≤ 100 ms or use opacity-only fades — do not simply disable animation entirely, as that can feel abrupt.

---

## 23. Mobile Interaction Patterns

Prefer mobile-native patterns:

- Bottom sheets
- Full-screen dialogs
- Sticky action bars
- Bottom navigation
- Swipe gestures, where genuinely useful (not gratuitous)
- Large touch targets

Avoid tiny dropdowns or controls that are hard to hit with a finger. Forms should minimise scrolling and typing on mobile specifically (e.g. pickers/toggles over free text where possible).

---

## 24. Terminology Reference

Use language a normal collector would understand. This table is authoritative — when internal/technical language and user-facing language conflict, user-facing wins in all UI copy, error messages, empty states, and labels.

| Internal / technical concept | User-facing language                                         |
| ---------------------------- | ------------------------------------------------------------ |
| Entity / Node                | Item / Person / Place _(use the specific type)_              |
| Relationship / Edge          | Connection                                                   |
| Metadata                     | Details / Information                                        |
| Schema                       | _(not surfaced)_                                             |
| Graph                        | Connections _(standard UI)_ / Explore _(advanced view only)_ |
| Query                        | Search                                                       |
| Record                       | Item                                                         |
| CRUD                         | _(not surfaced)_                                             |
| Foreign key                  | _(not surfaced)_                                             |
| UUID                         | _(not surfaced)_                                             |

> Note: "Explore" is the nav destination for the advanced connections/graph experience (§6); "Connections" is the label used for relationship data within a normal item view (§17). Don't use them interchangeably in copy — Explore is a _place_, Connections is a _kind of information_.

---

## 25. Consistency

The same concept looks and behaves the same way everywhere:

- Item titles use identical typography across all contexts.
- Primary actions share one consistent visual treatment app-wide.
- Editing behaves the same way regardless of item type.
- Search behaves identically everywhere it appears.
- Mobile navigation stays predictable across screens.

When an existing pattern already solves a problem, reuse it — don't invent a variant.

---

## 26. Quick-Reference Checklist (for implementation / review)

Use this when building or reviewing a screen:

- [ ] No raw technical terms visible (check against §24 table)
- [ ] Schema and custom fields use plain-language "kind" pickers, never raw type strings or dev abbreviations like "Req" (§16a, §16b)
- [ ] Required fields are visually flagged only — never block save (§16a)
- [ ] Field kinds are consistent between schema fields and freeform fields — same picker, same widgets (§16a, §16b)
- [ ] One clear primary action on screen
- [ ] Works with zero required configuration for a first-time user
- [ ] First-run empty state uses warm CTA, no setup wizard or dismissal modal (§3.6)
- [ ] Mobile layout designed independently, not shrunk from desktop
- [ ] Tablet layout uses collapsed/drawer navigation — not a scaled-down sidebar (§5)
- [ ] Touch targets meet minimum comfortable size even if visually compact
- [ ] Empty state (if any) answers "what do I do now?"
- [ ] Filter empty states explain why and offer to clear the filter (§7a)
- [ ] Image placeholders shown for items without images — layout does not collapse (§7b)
- [ ] Text truncation follows the rules for the context (card, list, detail) — no mid-word breaks (§7c)
- [ ] Bulk actions enter selection mode explicitly — never the default (§7d)
- [ ] Errors are user-readable with a recovery action
- [ ] Network errors have distinct, user-readable messages with retry actions (§12a)
- [ ] Background failures degrade silently without interrupting the user (§12a)
- [ ] Loading states use skeletons for known layouts, spinners for unknown (§13a)
- [ ] No loading indicator shown for operations expected under 300 ms (§13a)
- [ ] Destructive actions use confirmation or Undo (5-second window), not both (§14)
- [ ] Colour is never the sole carrier of meaning — verified in both light and dark themes (§20, §21a)
- [ ] Focus is managed after every significant action — never lost to body or invisible element (§20a)
- [ ] Dialogs and sheets trap focus while open and return focus to trigger on close (§20a)
- [ ] Keyboard nav + focus states verified
- [ ] `prefers-reduced-motion` respected — transitions shortened to opacity fades, not removed (§22)
- [ ] Scroll/filter/sort/search/view-mode state preserved on back-navigation within the same session/tab (§19)
- [ ] Direct-link entry loads collection at default state, not a reconstructed session (§19)
- [ ] "Recently added" = 30 days, "Recently viewed" = 7 days — no other values used (§18a)
