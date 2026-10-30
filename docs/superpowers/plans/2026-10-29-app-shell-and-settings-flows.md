# App shell, inline search and calmer settings flows Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (the user chose inline execution) or superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One collapsible app sidebar with a burger, a real inline search field in the top bar, collapsible groups, and settings flows (item types, relationship types, saved fields, admin settings) that open heavy editors in modals.

**Architecture:** A sidebar state store plus an `AppSidebar` component replace `manage-shell.svelte` and the header icon nav. The existing `search-palette.svelte` stays the single implementation of search and gets an `inline` host mode (dropdown under the top-bar field) next to its dialog host. A `CollapsibleSection` wrapper with remembered state is the one grouping primitive.

**Tech Stack:** SvelteKit SPA (Svelte 5 runes), Tailwind v4.3, shadcn-svelte/bits-ui, Vitest (server-render tests), Playwright e2e.

**Spec:** `docs/superpowers/specs/2026-10-29-app-shell-and-settings-flows-design.md` (builds on `2026-10-29-compact-wide-ui-design.md`, already implemented).

## Global Constraints

- `AGENTS.md` rules: Svelte 5 runes, `resolve()` for hrefs, British English, collector-facing terms, no `git add`/`git commit` by the agent, `--mode agent` for poe checks; run `poe format-frontend` before lint.
- Sidebar widths: expanded `w-56`, rail `w-12`. Defaults: expanded from 1280px, rail from 768px, drawer below 768px. State remembered per device in `localStorage` behind try/catch.
- Phones keep the bottom bar and 44px targets; every rail icon has a tooltip and the same accessible name as its expanded label.
- Search keeps every result group, cap, shortcut (`/`, arrows, Enter, Esc) and the "See all results" row; touch and phones keep the full-screen sheet.
- Dirty modals ask before closing (reuse `confirm-dialog.svelte`); focus returns to the opener (design §20a).
- Accessible names used by e2e (`openNav`, `searchButton`, `openSearch`) stay valid; change the helpers once, not each spec.

## Review Focus

- A collapsed or hidden sidebar must still let a keyboard user reach every destination (Task 3).
- Search blur-to-close must not swallow a click on a result row (Task 4).
- Closing a dirty editor modal must not lose edits silently (Task 5).
- `localStorage` unavailable must not break the sidebar or collapsible sections (Tasks 1, 2).
- Phones and touch tablets must not get the inline dropdown (Task 4).

---

### Task 1: Remembered collapsible sections

**Files:**
- Create: `frontend/src/lib/remembered.ts`, `frontend/src/lib/components/collapsible-section.svelte`
- Test: `frontend/tests/remembered.test.ts`, `frontend/tests/collapsible-section.test.ts`

**Interfaces:**
- Produces `remembered.ts`: `readFlag(key: string, fallback: boolean): boolean` and `writeFlag(key: string, value: boolean): void`, both swallowing storage errors; keys are namespaced `menagerist:`.
- Produces `CollapsibleSection` props `{ title: string; count?: number; id: string; defaultOpen?: boolean; class?: string; children: Snippet; actions?: Snippet }`. Renders a heading button with chevron (`aria-expanded`), the count, and the optional actions; open state persisted under `section:<id>`.

- [ ] **Step 1: Write `remembered.test.ts`** with a stubbed `localStorage`: `reads the fallback when nothing is stored`, `round-trips a flag`, `falls back when storage throws` (getItem and setItem both throw), `namespaces keys`. Run `npx vitest run tests/remembered.test.ts`; expected FAIL, module missing.
- [ ] **Step 2: Implement `remembered.ts`.** Expected: PASS.
- [ ] **Step 3: Write `collapsible-section.test.ts`** (server render, tooltip/bits mocks as in `tests/icon-button.test.ts`; `ui/collapsible` may need a mock like `tests/mocks/tooltip/*`): `renders the title and count`, `is open by default when defaultOpen`, `renders aria-expanded matching the state`. Expected FAIL.
- [ ] **Step 4: Implement `collapsible-section.svelte`** on `$lib/components/ui/collapsible`, reading the initial state with `readFlag` and writing on change. Expected PASS; then lint and typecheck.
- [ ] **Step 5: Leave uncommitted.** Suggested message: `feat(frontend): add remembered collapsible sections`.

### Task 2: Sidebar state store and nav model

**Files:**
- Create: `frontend/src/lib/sidebar.svelte.ts`
- Modify: `frontend/src/lib/manage-nav.ts` (add the main destinations), `frontend/tests/manage-nav.test.ts`
- Test: `frontend/tests/sidebar.test.ts`

**Interfaces:**
- Produces `sidebar.svelte.ts`: `type SidebarMode = 'expanded' | 'rail' | 'drawer'`; `defaultMode(width: number): SidebarMode` (≥1280 expanded, ≥768 rail, else drawer); class `SidebarController` with `mode` (derived from viewport width and the stored preference), `drawerOpen`, `toggle()` (expanded↔rail on wide screens, opens/closes the drawer on narrow), `closeDrawer()`; exported singleton `sidebar`.
- Produces `manage-nav.ts`: `mainDestinations: ManageItem[]` for Home `/`, Items `/items`, Collections `/collections`, Explore `/explore`; `activeManageHref` also matches `/` exactly and `/items` prefixes for those.

- [ ] **Step 1: Write `sidebar.test.ts`**: `defaultMode picks expanded, rail and drawer by width`, `a stored preference overrides the default on wide screens`, `toggle flips expanded and rail and remembers it`, `toggle opens and closes the drawer on narrow screens`, `works when storage throws`. Extend `manage-nav.test.ts`: `main destinations come first and match by path`. Expected FAIL.
- [ ] **Step 2: Implement.** Expected PASS; lint and typecheck.
- [ ] **Step 3: Leave uncommitted.** Suggested message: `feat(frontend): add sidebar state and main destinations`.

### Task 3: App sidebar, burger and top bar shell

**Files:**
- Create: `frontend/src/lib/components/app-sidebar.svelte`
- Modify: `frontend/src/routes/+layout.svelte` (header becomes burger, logo, search slot, New item, theme, account; remove the icon nav; render `AppSidebar`; remove `ManageShell` use), `frontend/src/lib/components/user-menu.svelte` (add Settings and API docs entries)
- Delete: `frontend/src/lib/components/manage-shell.svelte`
- Modify: `frontend/tests/e2e/helpers.ts` (`openNav` follows the sidebar on desktop, the bottom bar on phones), `frontend/tests/e2e/layout.desktop.spec.ts`, `frontend/tests/e2e/manage-shell.spec.ts` (rename to `app-sidebar.spec.ts`)
- Test: `frontend/tests/e2e/app-sidebar.spec.ts`

**Interfaces:**
- Consumes `sidebar` (Task 2), `manageGroups`/`mainDestinations` (Task 2), `CollapsibleSection` (Task 1) for the Library and System groups (ids `nav-library`, `nav-system`).
- Produces `AppSidebar` with no props (reads `sidebar`, `auth` and `page`); in `rail` mode renders icon links wrapped in tooltips; in `drawer` mode renders a modal-style drawer with a scrim that closes on navigation and on Esc.

- [ ] **Step 1: Write `app-sidebar.spec.ts`** (desktop at 2048×1152 unless stated): `the sidebar shows the main destinations and groups on every signed-in page`; `the burger collapses it to a rail and expands it again` (rail links keep their accessible names; width changes between about 224px and 48px); `the choice survives a reload`; `a member does not see admin entries`; `below 768px the burger opens a drawer that closes after choosing a destination`; `the sidebar is absent when signed out`; `every destination is reachable by keyboard in the rail` (Tab to the first rail link, Enter follows it). Expected FAIL.
- [ ] **Step 2: Implement `app-sidebar.svelte`** (a `<nav aria-label="Main">`; groups via `CollapsibleSection`, forced open on the active route's group) and restructure `+layout.svelte`: top bar with burger `IconButton` (label "Menu"), logo, search slot, New item, theme, account; sidebar column beside `#main-scroll` from `md`; bottom bar unchanged on phones. Delete `manage-shell.svelte`; the `PAGE_ALIGN` context is set by the layout wrapper beside the sidebar (non-fluid pages stay left-aligned there).
- [ ] **Step 3: Update e2e helpers and affected specs** (`layout.desktop`, `search-palette` button lookups, `keyboard-shortcuts`, the specs that scoped hub-card selectors to `main`): run `poe test-e2e -w 4 --skip-build` for them plus the `mobile` project specs. Expected PASS.
- [ ] **Step 4: Leave uncommitted.** Suggested message: `feat(frontend): collapsible app sidebar with burger`.

### Task 4: Inline search in the top bar

**Files:**
- Modify: `frontend/src/lib/components/search-palette.svelte` (add `inline` host mode), `frontend/src/lib/search-palette.svelte.ts` (controller exposes `inline: boolean` set by the layout), `frontend/src/routes/+layout.svelte`
- Test: `frontend/tests/e2e/search-palette.spec.ts` (update), `frontend/tests/search-palette.test.ts` (extend if view logic moves)

**Interfaces:**
- `SearchPalette` takes `inline?: boolean`. Inline: renders a relatively positioned host containing the `Command.Input` (the top-bar field, placeholder `Search everything…`, `aria-label="Search"`) and the results as an absolutely positioned dropdown (`top-full`, `z-50`, rounded, bordered, `max-h-[70dvh]`) shown while the controller is open. Dialog mode is unchanged and used on touch devices and below `md`.
- The layout mounts the inline instance in the top bar when `(pointer: fine)` and `md` and up, and the dialog instance otherwise; the `/` shortcut calls `searchPaletteController.show()`, which focuses the inline field.

- [ ] **Step 1: Update `search-palette.spec.ts`** first so it expects the new desktop behaviour: `popup(page)` is the search host (the field plus its dropdown), not a dialog; add `slash focuses the top-bar field and shows the hint`, `typing shows results beneath the field`, `clicking a result opens it (blur does not swallow the click)`, `Escape clears and closes`, `clicking outside closes`, `See all results opens the items page`; keep the dialog-mode cases under the `mobile` project (`search-palette` is already desktop-only; add `search-palette.mobile.spec.ts` for the sheet). Expected FAIL on the inline cases.
- [ ] **Step 2: Implement inline mode.** Share one `Command.Root` snippet between hosts; in inline mode close on `focusout` when `relatedTarget` is outside the host (list items use `onmousedown` preventDefault so a click is not lost), Esc clears then closes, and the dropdown is hidden while the field is focused with an empty query except for the hint. Keep every group, cap and "See all" row.
- [ ] **Step 3: Run** `poe test-e2e -w 4 --skip-build tests/e2e/search-palette.spec.ts tests/e2e/keyboard-shortcuts.spec.ts` plus the new mobile spec under the `mobile` project; `poe test-frontend`. Expected PASS.
- [ ] **Step 4: Leave uncommitted.** Suggested message: `feat(frontend): inline global search in the top bar`.

### Task 5: Item types and relationship types as list plus modal

**Files:**
- Modify: `frontend/src/routes/settings/item-types/+page.svelte`, `frontend/src/routes/settings/relationships/+page.svelte`
- Create: `frontend/src/lib/components/type-editor-dialog.svelte` (shared create/edit dialog around `SchemaEditor`)
- Test: `frontend/tests/e2e/manage-item-types.spec.ts` (update), `frontend/tests/e2e/type-editor-dialog.spec.ts` (new)

**Interfaces:**
- `TypeEditorDialog` props `{ open: boolean; kind: 'node' | 'edge'; typeId?: string; title: string; ... }` using `responsive-dialog` (size `lg`); closing with unsaved changes opens `ConfirmDialog` ("Discard changes?").

- [ ] **Step 1: Write `type-editor-dialog.spec.ts`**: `New item type opens an editor in a dialog and creates the type`, `Edit opens the same editor with the type's values`, `closing a changed editor asks before discarding`, `Escape on a clean editor closes it without asking`, plus the relationship-types equivalent. Update `manage-item-types.spec.ts` selectors for the list and the dialog. Expected FAIL.
- [ ] **Step 2: Implement the dialog and re-lay the pages** as compact lists (name, description, field count, "Example" badge; icon-only Edit/Delete via `IconButton`; a New `IconButton` in the page header; a search field when more than 8 types). Remove the always-visible create card and inline expansion.
- [ ] **Step 3: Run** the two specs, `examples-*` specs (they touch types) and `poe test-frontend`. Expected PASS.
- [ ] **Step 4: Leave uncommitted.** Suggested message: `feat(frontend): edit item and relationship types in a dialog`.

### Task 6: Saved fields and admin settings

**Files:**
- Modify: `frontend/src/routes/settings/saved-fields/+page.svelte`, `frontend/src/routes/admin/settings/+page.svelte`
- Test: `frontend/tests/e2e/saved-fields.spec.ts` (new, or extend the existing spec that covers presets), `frontend/tests/e2e/admin-settings.spec.ts` (update)

- [ ] **Step 1: Write the specs**: saved fields: `sections are collapsible and remember their state across a reload`, `Import and Export live in the More menu`, `row actions keep their accessible names`; admin settings: `groups are collapsible with the first open`, `Save and Reset appear only after a change`, `Reset restores the stored value`. Expected FAIL.
- [ ] **Step 2: Implement**: wrap each saved-fields section and each admin-settings group in `CollapsibleSection` (ids `saved-fields-<kind>`, `admin-settings-<group>`); move Import and Export into a `DropdownMenu` "More" button beside the title; turn row actions into `IconButton`s with an overflow menu for the rarer ones; admin settings rows become label-left/control-right with Save and Reset rendered only while the row differs from its stored value.
- [ ] **Step 3: Run** both specs, `backups.spec.ts`, `poe test-frontend`. Expected PASS.
- [ ] **Step 4: Leave uncommitted.** Suggested message: `feat(frontend): collapsible saved fields and admin settings`.

### Task 7: Remaining groups, docs and final verification

**Files:**
- Modify: Home (`frontend/src/routes/+page.svelte` sections use `CollapsibleSection`), `frontend/DESIGN_GUIDELINES.md` (§§5, 6, 8, 15, 21), `frontend/README.md` (key patterns: sidebar, inline search, `CollapsibleSection`), the two spec files under `docs/superpowers/specs/` (mark the first spec's settings sidebar and icon header as superseded)

- [ ] **Step 1: Apply `CollapsibleSection`** to the Home sections that list items; update the docs; format.
- [ ] **Step 2: Visual pass** (throwaway Playwright screenshots into the scratchpad, deleted afterwards) at 360, 1280, 2048 and 2560px: sidebar expanded and rail, drawer open, search dropdown open, item types list and dialog, saved fields, admin settings.
- [ ] **Step 3: Final gate** `poe lint-frontend`, `poe typecheck-frontend`, `poe test-frontend`, `poe test-e2e` (all `--mode agent` where supported); then the whole-branch review of everything since the first plan; fix Critical and Important findings with a failing test first; list rulings and deferred minors in the final message.
- [ ] **Step 4: Leave uncommitted.** Suggested message: `docs(frontend): record the app shell and settings flows`.
