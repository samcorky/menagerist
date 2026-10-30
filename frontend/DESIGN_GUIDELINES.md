# Menagerist Frontend Design Guidelines

Binding product and UX rules for contributors and coding agents. Engineering patterns belong in [README.md](README.md); implementation rationale belongs in [DECISIONS.md](../docs/DECISIONS.md).

## Reading guide

For UI work, read §§1–3 and §24, then the sections relevant to the change. These are requirements, not a claim that every feature is already implemented; do not expand a task to build unrelated features.

| Working on                                  | Read                                |
| ------------------------------------------- | ----------------------------------- |
| Layout or navigation                        | §§4–6, 19, 23                       |
| Browsing, cards, filters or search          | §§7–8, 18–19                        |
| Adding, editing or custom fields            | §§9–10, 15–17                       |
| Empty, error, loading or destructive states | §§11–14                             |
| Controls, keyboard, themes or motion        | §§20–22                             |
| Reviewing a screen                          | §26 and the relevant sections above |

Section numbers are retained for existing design references.

## 1. Purpose

Menagerist makes personal collections and knowledge approachable without requiring users to understand the underlying graph model. Users discover advanced capabilities when useful; basic collection management needs no configuration.

## 2. Design System (binding)

Use shadcn-svelte (preset `bK0zvfkNE`), Tailwind CSS and Lucide icons. Reuse existing components and compose established patterns before creating bespoke UI. Use the existing colour, spacing and component tokens; do not introduce competing scales. Fixed-choice value pickers use native selects (§15).

## 3. Core Principles

### 3.1 Plain language

Use the terminology in §24. Users should not need database, schema or query knowledge.

### 3.2 Collection first

Images, titles and identifying information take priority over metadata and controls. Aim for a calm, compact collection experience rather than an admin panel (§21).

### 3.3 Progressive disclosure

Adding, finding, viewing and editing an item must work with zero setup. Put advanced or rarely used options behind expandable sections.

### 3.4 Minimise decisions

Infer, suggest or default where reasonable. Start with “Add item”, not a sequence of type, collection, schema and template choices.

### 3.5 One obvious action per screen

Collection → Add item; first-run empty collection → Add your first item; search → Search your collection; item detail → Edit; missing information → Add information.

### 3.6 First-run experience

The empty collection is the onboarding: show a warm “Add your first item” action, without a setup wizard, tour or dismissal modal. Do not require category, field or collection configuration first. If items previously existed or were recently deleted, use the standard empty state (§11).

## 4. Mobile First

Design for touch from the start: short forms, little typing and no horizontal scrolling for normal content. Generous 44px hit areas and visible text labels apply to coarse pointers (`pointer-coarse:`); with a mouse or trackpad the compact sizes apply (§21). Use responsive image grids and the interaction patterns in §23.

## 5. Responsive Layout

| Viewport | Navigation and layout                                                                   |
| -------- | --------------------------------------------------------------------------------------- |
| Desktop  | App sidebar, expanded from 1280px; the burger collapses it to an icon rail              |
| Tablet   | Icon rail from 768px; do not reproduce the full desktop sidebar                         |
| Mobile   | Compact header with a burger that opens the sidebar as a drawer, plus bottom navigation |

Pages choose one of four widths: `fluid` for grids, tables and dashboards (capped at 2200px and centred beyond it), `reading` (64rem) for item detail and list-style settings, `form` (48rem) for short forms and `narrow` (24rem) for sign-in and setup. Tile grids add columns as the screen widens instead of stretching tiles. The app sidebar holds Home, Items, Collections and Explore, then collapsible Library, Account and System groups (Administration entries only for accounts with the permission), with Settings and API docs at the bottom. Its state is remembered per device; phones keep the bottom bar as well. Rail items have tooltips and the same accessible names as the expanded labels.

**Home** is a dashboard: totals (exact counts from the server, "1,000+" never needed below 100,000), Newly added (the true newest items), Tidy up (No photo, No description, Not in any collection, No item type; each opens the Items page with exactly that filter) and blocks for collections, item types in use and recently edited items. Every figure comes from a server count or a server-sorted list, never from a partly loaded one, and counts only item types the person actually uses. **The item page** shows the cover in a sticky left column from 1024px, with the details beside it and, from 1536px, a side panel for connections, collections and files; below 1024px it is one column with the cover first. An item with no cover keeps the column, holding the type placeholder and "Add a photo" (§7b). **Surprise me** (a shuffle icon button on Home and on a collection's header) opens a random item: any of yours on Home, only that collection's on a collection page, and says "Nothing to pick from yet" instead of navigating when there is none.

Uniform, scannable lists in settings and admin (users, devices, backups, scheduled tasks, recently deleted) are tables from the `md` breakpoint up and stacked cards below it. Use `DataTable` with `wide` from `$lib/viewport.svelte` so only one layout exists in the DOM; keep every row's action reachable by the same accessible name in both.

## 6. Navigation

Core destinations are **Collection**, **Search** and **Explore**. Keep “Add item” easy to find at every breakpoint. Settings stay visually secondary (the bottom of the sidebar); occasional features appear contextually rather than becoming navigation destinations. The top bar holds the burger, the logo, the search field, New item, the theme toggle and the account menu.

## 7. Collection View

Support grid/list views, search, filtering, sorting, infinite scrolling and responsive layouts. Default to a visual grid. Cards show enough to identify an item; avoid excessive metadata, badges, controls or decoration.

An item type may choose up to **three highlighted fields**, excluding long text. Show at most **two on grid cards**, **three on list cards**; omit empty values. Cover and title retain priority. Highlights use single-line truncation (§7c).

### 7a. Filtering

- Use chips or a panel, not query expressions or a query builder.
- Offer values present in the user's collection. Combine filters with AND behaviour expressed in plain language.
- Keep active filters visible, individually removable and clearable together.
- Use labels such as “Signed”, “Format: Blu-ray” and “From the 1990s”.
- Zero results explain the filter effect and offer to clear the relevant filters.

### 7b. Image Handling

- Keep one aspect ratio within each collection grid. Default to **2:3**; category types may specify another ratio (for example 16:9 or 1:1).
- Missing, loading and broken images use a full-size placeholder showing the item type's icon in its colour (a type with none, or an untyped item, shows the generic package icon in the neutral tone). Never collapse the card or show a broken-image icon.
- On the item page the placeholder fills the cover column and carries an "Add a photo" drop-or-browse area that uploads and sets the cover, so a missing cover is an invitation rather than a gap.
- Lazy-load images without blocking cards. Fade loaded images in over **150 ms**, or show instantly for reduced motion.
- Placeholders must work in both themes.

### 7c. Truncation Rules

| Content                                                         | Treatment                                                |
| --------------------------------------------------------------- | -------------------------------------------------------- |
| Card/list titles, card secondary information, connection labels | One line with end ellipsis                               |
| Detail titles                                                   | Wrap fully; never truncate                               |
| Card descriptions/long text                                     | Omit                                                     |
| Detail descriptions/long text                                   | Full text, or “Show more” beyond roughly five lines      |
| Tags/chips                                                      | Fixed maximum width, ellipsis, full label on hover/focus |

Break at word boundaries before the ellipsis. Make full truncated content available on hover/focus, tap/long-press, or the detail view.

### 7d. Bulk Actions

Enter selection explicitly through Select, mobile long-press or desktop checkbox reveal; never make selection the default. Show selection controls, a count, Select all and an exit without acting. Support delete, tag and, where applicable, remove from collection/move to category.

Bulk deletion follows §14 (“X items deleted → Undo”). On mobile use a bottom action bar, not a precision dropdown.

## 8. Search

With a mouse on a screen at least 768px wide, search is the field in the top bar and its results open in a dropdown beneath it: `/` focuses it, arrows and Enter choose, Escape clears the text and then closes it. Touch devices and phones keep the full-screen search sheet.

Search is fast, forgiving and natural-language friendly: examples include “matrix”, “signed items”, “things from 1999”, “keanu reeves” and “recently added”. Never require query syntax; offer useful fuzzy/browsable results where possible.

Search the name, description and every text/number detail, including fields absent from cards. Explain hidden-field matches in one muted line, for example “Matched in Director: Ridley Scott”. Group result kinds where useful using collector-facing names (Items, People, Collections, Tags).

## 9. Adding Items

Start with an item name and Continue, not a large form. Infer the type, suggest/enrich information, apply defaults and avoid duplicate questions. Optional information can be skipped.

### 9a. Item Type Detection

Choosing a type is one searchable picker everywhere (new item, Quick capture, and the item page while it has no type): the types you have items in come first under "In use" with their counts, the rest under "Other item types", and typing a name that matches nothing offers `Create "name"`, which creates and selects it in one step. Each type can have an icon and a colour (a fixed palette), set in the type editor with a search over the available icons, a name shown on hover or focus, and a dice button that picks both at random.

Detect from the name on a best-effort basis. Prefill confident matches; show ambiguous suggestions inline for correction; fall back to a generic item when detection fails. Always allow changes and use category names, not internal identifiers. Detection never blocks progress.

Incomplete data is better than blocking a save. Only information truly necessary for a record to exist (for example its name) may block creation; category “required” fields are advisory (§16a).

## 10. Editing Items

An item's type can be changed or removed at any time from the picker under its name (the same picker as §9a, with "No item type"). Values are never deleted by a type change. When the new type has no field for some of the item's values, a confirmation lists them and says they stay on the item as plain fields; otherwise the change applies at once with an Undo in the toast (§14). If the item has a field of its own with the same name as a field of the new type, the change is refused with an explanation instead of guessing which wins.

Put important information first. Group advanced or rarely used information into expandable sections; do not show a wall of empty fields. Keep the experience consistent across item types.

## 11. Empty States

Explain what the user can do next and provide the action. Distinguish first use (§3.6), an emptied collection and a search/filter with no matches (§7a). “No items found” alone is insufficient.

## 12. Errors

Use readable explanations and recovery actions, never raw exceptions, HTTP codes or backend identifiers. Tie validation feedback to the relevant field: “We couldn't save this item. Check the highlighted information and try again.” Preserve entered data.

### 12a. Network & Offline States

Menagerist requires a connection; do not queue offline writes or add offline synchronisation.

- Distinguish detectable offline failures from server/unknown failures, with Retry or reload guidance.
- Failed reads keep available cached/stale content visible and mark it as potentially out of date; do not block the whole interface.
- Failed writes show an error at the action site.
- Non-critical background failures, such as enrichment lookups, fall back quietly without interrupting the flow.

## 13. Feedback

Give meaningful actions lightweight feedback. Use inline feedback for visible results and field errors; toasts for out-of-view/background completions and Undo. Routine confirmations do not need modals. Toasts announce themselves without taking focus (§20a).

### 13a. Loading States

- No indicator for operations expected under **300 ms**; provide one for operations that may take longer.
- Known layouts/initial content use matching skeletons; unknown layouts or in-place actions use spinners. Never show both together.
- Inline actions show progress on their trigger. Full-page loaders are only for hard navigation with no partial content available.
- Reduce or remove skeleton shimmer for reduced motion; keep the placeholder shape.

## 14. Confirmation vs. Undo

Do not confirm harmless or easily reversible actions. Prefer Undo for reversible destructive actions; use confirmation for irreversible, hard-to-undo or surprising actions, explaining what is lost. Do not require both confirmation and Undo for the same action.

Undo toasts last **5 seconds**. Defer the destructive action until the timeout or navigation away, whichever comes first; navigation commits immediately. Use the same window for single/bulk deletions and connection removal.

Removing a saved category field archives it and preserves its values. Restore it through “Removed fields”; only permanent deletion of its values needs confirmation. Unsaved fields can simply be removed.

## 15. Forms

Use clear labels, useful explanations, sensible defaults and few required fields. Preserve input after validation failures. Validate at useful moments rather than every keystroke, with helpful copy.

Heavy create and edit forms (a type with its fields, for example) open in a large dialog from a compact list, rather than expanding inline; on phones the dialog is a full-screen sheet. Closing an editor with unsaved changes asks "Discard changes?" first. Content that is grouped on a page (sections of presets, groups of settings, sections on Home) sits under a collapsible heading whose open state is remembered.

Fixed-choice value pickers default to **native `<select>`** (`ui/native-select`) for mobile and accessibility support. Exceptions:

- Searchable or rich options need a suitable custom picker.
- Actions use `DropdownMenu`, not a value select.
- Open-ended, user-authored options (such as categories with “+ New”) use a chip/search picker.

## 16. Metadata Presentation

Show “Details” or “Information”, with readable labels and values. Hide internal keys, raw type strings, database types, foreign keys and UUIDs (§24). Optional data stays optional throughout an item's life.

Categories and relationship types may define suggested fields; this collector-authored concept can be shown without exposing JSON Schema internals. Types without a schema remain fully freeform.

### 16a. Category & Relationship-Type Schemas

Define fields once in **Settings → Categories / Relationships**, not per item. Show category fields prominently and item-specific custom fields underneath.

Each field has a **Label**, a plain-language **Kind** and an optional **Required** flag. Derive internal keys; never ask the user to enter them. Use full labels, not abbreviations such as “Req”.

| Kind      | Entry widget                                    |
| --------- | ----------------------------------------------- |
| Text      | Single-line input                               |
| Long text | Multi-line input                                |
| Number    | Numeric input                                   |
| Yes/No    | Toggle switch                                   |
| Choice    | Select or radio buttons                         |
| Date      | Date picker                                     |
| Rating    | Stars, numeric scale or slider, where supported |

This is an interaction reference, not an exhaustive inventory of shipped kinds. For supported kinds and extension mechanics, see [field-types.md](../docs/field-types.md). Use the same kinds and widgets for category fields and freeform details.

**Required is a completeness signal, never a save constraint.** Flag missing information visually or through an appropriate smart group. Attribute values still undergo validation; advisory required flags do not block saves. The distinction is recorded in [DECISIONS.md](../docs/DECISIONS.md).

### 16b. Freeform Custom Fields

Any item can have additional fields, using the same Label + Kind flow. They do not change the category schema. Repeated labels may suggest a category field, but do not automatically formalise them or nag the user.

Generate hidden keys so duplicate labels cannot collide or overwrite category fields. Labels have no name-length limit. Allow at most **50 extra details** per item and preserve their insertion order across saves.

## 17. Relationships & Connections

Show connections in natural language: the connected item's name and relationship (“Keanu Reeves — Actor”), not graph structure. Standard UI follows §24. A deliberately advanced Explore experience may use technical framing only where explicitly appropriate; prefer “Connections map” even there.

A relationship type may highlight up to **two fields** on one muted line below the connected name. Its edit button opens an **Edit connection** sheet using the same field widgets as items. Removal uses Undo (§14).

## 18. Smart Groups

Surface useful groups automatically rather than requiring manual configuration: Recently added, Favourites, Signed items, Items missing information, Items from the 1990s, Most connected and Recently viewed. Explain membership in one line if the name is insufficient.

### 18a. Freshness Definitions

“Recently added” means **30 days**; “Recently viewed” means **7 days**. These are fixed defaults until user configuration is introduced. Use the same values everywhere and describe them in plain language.

## 19. Infinite Scrolling & State Preservation

Load large collections incrementally. Returning from an item in the same tab/session restores scroll position, filters, sort, search and grid/list mode exactly.

Do not share this state across tabs. Direct/deep links have no collection context to reconstruct: return to defaults. Surviving a hard reload is optional.

## 20. Accessibility

Provide semantic HTML, accessible labels/alternative text, full keyboard access, visible focus, screen-reader support, touch-friendly controls and WCAG-appropriate contrast in both themes. Important information always has an icon, label or text as well as colour. Respect reduced motion (§22).

### 20a. Focus Management

| Action                                | Focus destination                                                    |
| ------------------------------------- | -------------------------------------------------------------------- |
| Dialog/sheet opens                    | First focusable element inside; trap focus while open                |
| Dialog/sheet closes, including Escape | Trigger                                                              |
| Item deleted                          | Next item, then previous; if empty, list container or primary action |
| Toast or other non-modal update       | No automatic focus move; announce toasts with `aria-live`            |
| Form succeeds without navigation      | Confirmation or first field when resetting                           |
| Inline edit confirmed                 | Display value replacing the input                                    |
| Bulk selection entered/exited         | First selectable item / Select trigger                               |

Never leave focus on `<body>` or an invisible element. Move focus for user-triggered transitions, not passive count badges or inline updates.

### 20b. Keyboard Shortcuts

Every shortcut has a visible button, link or menu equivalent and a plain-language entry in the `?` overlay. Register only while applicable. Follow the registry implementation in [README.md](README.md#key-patterns).

Bare letters do not fire in fields, contenteditable areas or overlays (dialogs, listboxes, menus). Modified shortcuts such as Cmd/Ctrl+S may explicitly opt in. Escape belongs to the topmost layer and must not trigger an already-handled action. Layout-dependent `?` and `/` allow optional Shift. Abandoned key sequences never swallow typing or block input.

## 21. Visual Design

Keep chrome calm, clean, modern, compact and consistent. On a mouse, controls are 28-32px high with tight gaps and navigation, toolbar and row actions are icon-only with a tooltip and the same accessible name; touch devices show the label beside the icon at 44px. Buttons that commit or cancel a decision (Save, Cancel, Delete, Sign in) and empty-state calls to action keep their text. Let collection images and titles provide visual interest. Avoid excessive gradients, shadows, decorative animation, oversized headings/buttons, cards, badges and dense metadata.

### 21a. Dark Mode

Support light and dark themes through semantic tokens, with no off-system hard-coded colours. Verify contrast and non-colour meaning in each; ensure uploaded images work against either background. Follow system preference by default; a manual Settings override is optional.

## 22. Animation

Use subtle motion to explain state/hierarchy, not decoration or delays for repeat actions.

| Transition                     | Duration   |
| ------------------------------ | ---------- |
| Toggle, checkbox, badge        | 100–150 ms |
| Toast, chip, inline enter/exit | 150–200 ms |
| Panel/sheet                    | 200–250 ms |
| Page/route                     | 250–300 ms |

For reduced motion use transitions of at most **100 ms** or opacity-only fades; image loading may be instant (§7b) and skeleton shimmer reduced or removed (§13a).

## 23. Mobile Interaction Patterns

Prefer bottom sheets, full-screen dialogs/search where appropriate, sticky action bars and bottom navigation. Use swipes only where useful, avoid tiny dropdown targets and reduce typing/scrolling with suitable pickers and toggles. Layout rules are in §§4–5; native select guidance is in §15.

## 24. Terminology Reference

Authoritative for UI labels, copy, errors and empty states:

| Internal concept          | User-facing language                                                    |
| ------------------------- | ----------------------------------------------------------------------- |
| Entity / Node / Record    | Item, Person, Place or the specific type                                |
| Relationship / Edge       | Connection                                                              |
| Metadata                  | Details / Information                                                   |
| Schema                    | Suggested fields or category fields; hide implementation terminology    |
| Graph                     | Connections for information; Explore for the advanced destination (§17) |
| Query                     | Search                                                                  |
| CRUD / Foreign key / UUID | Do not surface                                                          |

**Explore is a place; Connections is information.** Do not use them interchangeably.

## 25. Consistency

Reuse existing treatments for item titles, primary actions, editing, search and navigation. Extend an established pattern before inventing a variant.

## 26. Quick-Reference Checklist (for implementation / review)

- [ ] Collector-facing language; no leaked implementation terms (§24).
- [ ] One primary action; basic use needs no configuration (§3).
- [ ] Appropriate layouts, controls and touch targets across breakpoints (§§4–6, 15, 23).
- [ ] Relevant empty, error, loading and recovery states; consistent confirmation/Undo (§§11–14).
- [ ] Keyboard, focus, screen readers, both themes and reduced motion checked (§§20–22).
- [ ] Feature-specific rules checked: cards/filters, fields, connections or navigation state as applicable.
