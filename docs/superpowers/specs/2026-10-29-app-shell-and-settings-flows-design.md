# App shell, inline search and calmer settings flows

Date: 2026-10-29. Status: draft for approval. Follows `2026-10-29-compact-wide-ui-design.md` (built, uncommitted) and replaces its settings-only sidebar and icon-only header nav.

## Intent

After the compact/wide pass the header is a row of bare icons, search is still a modal, and Settings has its own separate sidebar. The settings pages the user finds worst (admin settings, item types, relationship types, saved fields) pile every control on the page at once. The aim is one coherent shell with a real search field, and settings flows that show a list and open the heavy editors in modals.

## Goals

- One collapsible app sidebar on desktop (Home, Items, Collections, Explore, plus the Settings and Admin sections as collapsible groups), a drawer behind a burger on smaller screens.
- A real search field in the top bar that opens its results inline on desktop.
- Grouped content is collapsible everywhere it is grouped, with the open/closed state remembered.
- Heavy create/edit forms move into modals; pages show a compact list.

## Non-goals

- No change to what data or features exist, to the API, or to routes (URLs stay).
- No new navigation destinations; terminology stays per design §24.
- The item detail, collection and capture screens are not redesigned in this round (the user named four areas; others only get the shared collapsible-group rule where they already group content).

## Anti-goals

- Search must not get slower or lose a result type or keyboard shortcut (`/`, arrow keys, Enter, Esc) that the modal has today.
- Phones must keep the bottom bar and 44px targets; the burger adds to it, it does not replace it.
- A collapsed sidebar must not hide anything: every icon has a tooltip and the same accessible name as its expanded label.
- A modal must never trap unsaved work silently: closing a dirty editor asks first (reuse `ConfirmDialog`).

## Decisions

### 1. App sidebar

- Replaces `manage-shell.svelte` and the icon-only header navigation. The root layout renders it for every signed-in route; the Settings/Admin group and the `manage-nav.ts` model move into it unchanged (admin items still gated by permission).
- Contents, top to bottom: Home, Items, Collections, Explore; **Library** group (Item types, Relationship types, Saved fields, Examples, Recently deleted); **System** group (Status and the permitted Admin sections); Account at the bottom. Groups are collapsible and remember their state; the active route's group is open.
- Three states: expanded (`w-56`), icon rail (`w-12`, tooltips), hidden. The burger in the top bar toggles expanded and rail. Defaults: expanded from 1280px, rail from 768px, drawer below 768px (opened by the burger, closes on navigation). The chosen state is remembered per device in `localStorage`, guarded for it being unavailable.
- Phones keep the bottom bar (Home, Items, New, Search) as now.
- `IconButton`'s tooltip approach applies to rail items; on touch, drawer items show their text.

### 2. Top bar and search

- Top bar: burger, logo, a wide centred search field, New item (filled icon), theme, account menu. Settings and API docs move into the sidebar and the account menu.
- Desktop (`pointer: fine`, `md` and up): the field is the global search. Typing opens a results dropdown beneath it with the same groups, caps and sources as today's palette (`palette-search.ts`, `palette-sources.ts`); `/` focuses the field, Esc clears and closes, arrows and Enter pick a result, "See all results" goes to the existing results page. The modal `SearchPalette` is no longer opened from desktop.
- Touch and phones: the search icon opens today's full-screen search sheet unchanged.
- Builder decides how to share the result logic between the dropdown and the sheet (shared controller or extracted list component); it must not fork the search behaviour.

### 3. Collapsible groups

Any page section that groups several items gets a `Collapsible` header (title, count, chevron) with the state remembered per page in `localStorage`. First use: admin settings groups, saved fields sections, Status groups (already collapsible, keep), Home sections where they list items. One shared wrapper component (`collapsible-section.svelte`) so the behaviour is identical.

### 4. Settings flows

- **Item types and Relationship types:** the page is a compact list (name, description, field count, "example" badge) with a search box when there are many, row actions icon-only (Edit, Delete) and a New button in the page header. New and Edit open `SchemaEditor` in a large `responsive-dialog` (modal on desktop, full-screen sheet on phones). Inline expanding cards and the always-visible "New item type" card go away.
- **Saved fields:** each section (field presets, choice lists and so on) is a collapsible group; row actions collapse into icon buttons with an overflow menu for the rarer ones; Import and Export move into a single "More" menu beside the page title. Editing already uses a dialog and stays.
- **Admin settings:** groups become collapsible (first group open). Each setting is one compact row: label and description on the left, the control on the right; Save and Reset appear only while the row is changed (Reset as an icon button). No change to what can be configured.

## Constraints

- `AGENTS.md` rules apply (runes, `resolve()`, British English, no commits by the agent, `--mode agent` checks). The `touch-sizes` guard, accessible names and the e2e helpers (`openNav`, `searchButton`, `openSearch`) must keep working; where an e2e helper has to change to follow the new shell, change the helper once, not each spec.
- Dirty-editor protection and keyboard focus return (design §20a) apply to every new modal.

## Order of work

1. Shared pieces: `collapsible-section.svelte`; sidebar state store (`src/lib/sidebar.svelte.ts`); inline search results component.
2. App shell: sidebar, burger, top bar search; retire `manage-shell`; adapt e2e helpers.
3. Settings flows: item types, relationship types, saved fields, admin settings.
4. Docs (design §§5, 6, 8, 15, 21; frontend README), e2e fixes, visual pass at 360, 1280, 2048 and 2560px, then the whole-branch review of everything since the first plan.

## Left to the builder

Dropdown result layout details, sidebar widths and transition, exact row layouts in the new lists, which rarer row actions go in overflow menus.
