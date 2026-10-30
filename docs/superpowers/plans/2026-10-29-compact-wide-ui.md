# Compact, wide, icon-led desktop UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the desktop UI compact, full-width and icon-led, while phones and tablets keep their 44px touch targets and visible labels.

**Architecture:** Touch sizing becomes opt-in through Tailwind's `pointer-coarse:` variant, so desktop falls back to the already-compact Rhea primitives. Three new shared units carry the rest: `IconButton` (icon, tooltip, accessible name), `Page` (width and spacing per page type) and a manage-area sidebar shell (Settings, Admin, Recently deleted, Status). Existing pages then migrate onto them.

**Tech Stack:** SvelteKit SPA (Svelte 5 runes), Tailwind v4.3 (`pointer-coarse:` / `pointer-fine:` are available), shadcn-svelte `rhea` style on bits-ui, Lucide, Vitest (server-render component tests), Playwright e2e.

**Spec:** `docs/superpowers/specs/2026-10-29-compact-wide-ui-design.md`

## Global Constraints

- Design viewport 2048px wide (2560×1440 at 125%); must also work at 2560px, 1280px and a 360px phone. Below `lg` (1024px) layouts are today's single column.
- Touch (`pointer: coarse`) keeps 44px targets, visible text labels and the bottom nav. Desktop controls are 28–32px (`h-7`/`h-8`).
- No icon-only button without an accessible name. Accessible names stay exactly as today's visible text (e2e helpers use `getByRole(..., { name, exact: true })`).
- Buttons that commit or cancel (Save, Cancel, Delete, Sign in) and the single empty-state call to action keep their text.
- Widths: `fluid` capped at 2200px centred; `reading` `max-w-5xl`; `form` `max-w-3xl`; `narrow` `max-w-sm`. (Plan call: this tightens the spec's "72–80rem" reading cap to 64rem, because item detail and forms are narrow today; the spec is updated in Task 9.)
- Follow `AGENTS.md`: Svelte 5 runes, `resolve()` for hrefs, British English, collector-facing terms (design §24), no `git add` / `git commit` by the agent (each task ends by leaving changes uncommitted with a suggested commit message). Never hand-edit `src/lib/api/generated/`.
- Run frontend checks with `--mode agent`: `poe test-frontend`, `poe lint-frontend`, `poe typecheck-frontend`.

## Review Focus

- Phone and touch-emulated Chromium (`mobile` e2e project) must still see visible labels and 44px targets: pinned in Tasks 1, 2 and 9.
- A signed-out or password-expired user must not see the manage sidebar or any nav: pinned in Task 6.
- `/settings` and `/admin` hub pages must still render something useful inside the shell at `lg+`, and the hub list below `lg`: pinned in Task 6.
- A non-admin must not see Admin entries in the sidebar, and `/admin/*` routes stay guarded as today: pinned in Task 6.
- A very wide viewport (3440px) must not stretch grids or tiles beyond the ceiling: pinned in Task 4 and checked in Task 9.

---

### Task 1: Touch-size guard and sweep

**Files:**
- Create: `frontend/tests/touch-sizes.test.ts`
- Modify: the 26 files that match `h-11|min-h-11|size-11` under `frontend/src` (find with `grep -rln "h-11\|min-h-11\|size-11" frontend/src`)

**Interfaces:**
- Produces: the convention that a bare `h-11`, `min-h-11` or `size-11` is forbidden in `.svelte` files unless the element is touch-only (`md:hidden` bottom nav and `max-md:` blocks). Later tasks write `pointer-coarse:h-11` where a touch size is needed.

- [ ] **Step 1: Write `touch-sizes.test.ts`.** Read every `.svelte` file under `src` with `fs`, and fail for any class token `h-11`, `min-h-11`, `min-w-11` or `size-11` that is not prefixed with `pointer-coarse:` (or `max-md:` / `max-sm:`), except lines inside an explicit `ALLOWED` list of `{ file, reason }` entries (the bottom nav in `src/routes/+layout.svelte` is the only initial entry). Assert on the offending `file:line` list being empty so a failure names its locations.
- [ ] **Step 2: Run it to see it fail.** `cd frontend && npx vitest run tests/touch-sizes.test.ts`. Expected: FAIL, listing the offending lines in about 26 files.
- [ ] **Step 3: Sweep each listed file.** Replace `h-11` / `min-h-11` / `size-11` with `pointer-coarse:h-11` / `pointer-coarse:min-h-11` / `pointer-coarse:size-11`. Where the element is a plain `<a>`, `<button>` or `<div>` with no compact default, also give it an explicit compact desktop size (`h-8`, or `h-7` for toolbar items), otherwise it collapses to content height. Where the element is a `Button`, `Input` or other primitive, rely on the primitive's default. Also tighten page-level padding and gaps only in Task 4, not here.
- [ ] **Step 4: Run the guard and the unit suite.** `poe test-frontend --mode agent`. Expected: PASS.
- [ ] **Step 5: Look at it.** Start `poe serve-frontend` and view Items, Collections and Settings at 2048px with a mouse: controls are visibly shorter. Emulate a phone (Chrome devtools, touch) and confirm controls are still 44px.
- [ ] **Step 6: Leave uncommitted.** Suggested message: `refactor(frontend): make 44px touch targets opt-in via pointer-coarse`.

### Task 2: `IconButton`

**Files:**
- Create: `frontend/src/lib/components/icon-button.svelte`
- Test: `frontend/tests/icon-button.test.ts`

**Interfaces:**
- Produces: `IconButton` with props `label: string`, `shortcut?: string`, `variant?: ButtonVariant`, `href?: string`, `onclick?`, `class?`, `disabled?`, and a default `children` snippet holding the Lucide icon. It renders a `Button` wrapped in `ui/tooltip` (not `popover-tooltip`: a popover would swallow the tap on touch). The label is rendered as `<span class="sr-only pointer-coarse:not-sr-only">{label}</span>`, so the accessible name equals `label` on every device, and touch devices show icon plus text with `pointer-coarse:w-auto pointer-coarse:px-3 pointer-coarse:h-11`. The tooltip shows `label` and, when given, `shortcut`.
- Consumes: `Button` from `$lib/components/ui/button`, `Tooltip` from `$lib/components/ui/tooltip`.

- [ ] **Step 1: Write the failing tests** (server render, as in `tests/narrowed-bar.test.ts`, mocking `@lucide/svelte` with `tests/mocks/noop.svelte`): `renders the label as screen-reader text that touch devices reveal` (HTML contains `sr-only pointer-coarse:not-sr-only` around the label); `renders an anchor when href is given` (`<a` and the href); `renders a button without href`; `passes variant and class through`.
- [ ] **Step 2: Run to see them fail.** `npx vitest run tests/icon-button.test.ts`. Expected: FAIL, module missing.
- [ ] **Step 3: Implement `icon-button.svelte`** to the interface above, using runes and `{@render children?.()}`.
- [ ] **Step 4: Run again.** Expected: PASS. Then `poe lint-frontend --mode agent` and `poe typecheck-frontend --mode agent`.
- [ ] **Step 5: Leave uncommitted.** Suggested message: `feat(frontend): add IconButton with tooltip and touch label`.

### Task 3: Header shell

**Files:**
- Modify: `frontend/src/routes/+layout.svelte:187-268` (desktop header)
- Modify: `frontend/src/lib/components/theme-toggle.svelte`, `frontend/src/lib/components/user-menu.svelte` (drop their `h-11` leftovers if Task 1 did not already)
- Test: `frontend/tests/e2e/layout.desktop.spec.ts` (new)

**Interfaces:**
- Consumes: `IconButton` (Task 2).

- [ ] **Step 1: Write the e2e spec** `layout.desktop.spec.ts` (desktop project only): at 2048×1152, `the header spans the viewport` (the header's inner container width is at least 2000px); `header navigation is reachable by name` (`getByRole('link', { name: 'Home', exact: true })`, `Items`, `Collections`, `Settings`, and `getByRole('button', { name: 'Search', exact: true })` are visible); `hovering an icon shows its tooltip` (hover `Items`, expect a `role=tooltip` containing `Items`); `the header is compact` (header height under 52px).
- [ ] **Step 2: Run to see it fail.** `poe test-e2e --mode agent tests/e2e/layout.desktop.spec.ts`. Expected: FAIL on width and height.
- [ ] **Step 3: Restyle the header.** Remove `max-w-4xl`; use `px-4 py-1.5`. Convert Home, Items, Collections, API docs, Settings, Search and New item to `IconButton` (New item uses the default variant and `shortcut` from its existing registered shortcut; keep labels identical to today's text: "Home", "Items", "Collections", "API docs", "Settings", "Search", "New item"). Keep the logo with its wordmark. Highlight the active route with `variant="secondary"` as today. The mobile header and bottom nav are untouched.
- [ ] **Step 4: Run the spec and the existing nav specs.** `poe test-e2e --mode agent tests/e2e/layout.desktop.spec.ts tests/e2e/search-palette.spec.ts tests/e2e/keyboard-shortcuts.spec.ts`, plus `npx playwright test --project=mobile` for `collections.spec.ts` to prove `openNav` still works on a phone. Expected: PASS.
- [ ] **Step 5: Leave uncommitted.** Suggested message: `feat(frontend): full-width icon-only desktop header`.

### Task 4: `Page` component and user-facing page migration

**Files:**
- Create: `frontend/src/lib/components/page.svelte`
- Create: `frontend/tests/page.test.ts`
- Modify: `frontend/src/routes/+page.svelte:94`, `items/+page.svelte:450,613,637`, `collections/+page.svelte:277,313`, `collections/[id]/+page.svelte:944,1169,1190`, `explore/+page.svelte:10`, `items/[id]/+page.svelte:548`, `items/new/+page.svelte:141`, `login/+page.svelte:41`, `setup/+page.svelte:91`

**Interfaces:**
- Produces: `Page` with props `width?: 'fluid' | 'reading' | 'form' | 'narrow'` (default `'reading'`), `class?`, `children`. It renders `<main class="flex-1 px-4 py-4 sm:px-6 md:py-5">` containing `<div class="flex w-full flex-col gap-4 …">`, where the width class is `mx-auto max-w-[2200px]` (fluid), `mx-auto max-w-5xl` (reading), `mx-auto max-w-3xl` (form) or `mx-auto max-w-sm` (narrow). A context key `pageAlign` (`'center' | 'start'`, default `'center'`) lets a parent shell make non-fluid pages left-aligned; the manage shell (Task 6) sets `'start'`.
- Produces: grid helper class convention `grid-cols-[repeat(auto-fill,minmax(11rem,1fr))]` (tile grids) used by Items, collection view and Collections; the minimum tile width is tuned in the browser.

- [ ] **Step 1: Write `page.test.ts`** (server render): `fluid pages are capped at 2200px`; `reading pages use max-w-5xl`; `narrow pages use max-w-sm`; `start alignment drops the auto margins` (render with the context set).
- [ ] **Step 2: Run to see it fail.** Expected: FAIL, module missing.
- [ ] **Step 3: Implement `page.svelte`.**
- [ ] **Step 4: Run to see it pass.**
- [ ] **Step 5: Migrate the pages**, replacing each `<main …><div class="mx-auto flex max-w-… flex-col gap-N">` pair with `<Page width="…">`: Home, Items, Collections, collection view and Explore are `fluid`; item detail is `reading`; new item is `form`; login and setup are `narrow`. Replace the fixed `grid-cols-1 … lg:grid-cols-4` tile grids on Items and the collection view (both the loading skeleton and the real grid) with the auto-fill grid; tighten tile gaps to `gap-2`. Home's two `grid-cols-2 sm:grid-cols-3` grids use the same auto-fill grid.
- [ ] **Step 6: Verify.** `poe test-frontend --mode agent`, `poe typecheck-frontend --mode agent`, then in the browser at 1280, 2048 and 2560px (Items: more tiles per row as width grows) and at 3440px (content stops growing, centred at 2200px).
- [ ] **Step 7: Leave uncommitted.** Suggested message: `feat(frontend): fluid page widths and auto-fill tile grids`.

### Task 5: Icon-only toolbars and row actions (user-facing screens)

**Files:**
- Modify: `frontend/src/routes/items/+page.svelte`, `collections/+page.svelte`, `collections/[id]/+page.svelte`, `items/[id]/+page.svelte`, `explore/+page.svelte`, `+page.svelte`, `frontend/src/lib/components/narrowed-bar.svelte`, `node-grid-card.svelte`, `node-card.svelte`, `search-palette.svelte` where they contain labelled toolbar or row buttons
- Test: `frontend/tests/e2e/icon-buttons.spec.ts` (new)

**Interfaces:**
- Consumes: `IconButton` (Task 2).

- [ ] **Step 1: Write the e2e spec** (desktop and `mobile` projects): `toolbar buttons keep their accessible names` for the buttons you convert (list them from the page before changing it, then assert `getByRole('button', { name, exact: true })` for each); `desktop shows no visible text on toolbar icons` (the `sr-only` span's bounding box is 1×1 px); `touch shows the label` (in the `mobile` project the same span has a width above 8px). Keep decision buttons (Save, Cancel, Delete, Create, Add) untouched.
- [ ] **Step 2: Run to see it fail** on the "no visible text" and "touch shows the label" assertions for the converted buttons.
- [ ] **Step 3: Convert** filter, sort, view-toggle, select, edit, share, connect, overflow and similar toolbar/row actions to `IconButton`, keeping each label string exactly as the current visible text. Leave destructive confirmations and form submits as text buttons.
- [ ] **Step 4: Run** `poe test-e2e --mode agent` for `items`-, `collections`-, `create-item`-, `connect-items`-, `smart-collections`- and `advanced-search`-related specs, then `npx playwright test --project=mobile`. Fix any selector that depended on visible text.
- [ ] **Step 5: Leave uncommitted.** Suggested message: `feat(frontend): icon-only toolbars with tooltips on user-facing pages`.

### Task 6: Manage sidebar shell (Settings, Admin, Recently deleted, Status)

**Files:**
- Modify: `frontend/src/lib/viewport.svelte.ts` (add `export const desktop = new MediaQuery('min-width: 1024px')`)
- Create: `frontend/src/lib/manage-nav.ts`, `frontend/src/lib/components/manage-sidebar.svelte`
- Test: `frontend/tests/manage-nav.test.ts`
- Modify: `frontend/src/routes/+layout.svelte` (render the sidebar beside the page when appropriate), `frontend/src/routes/settings/+page.svelte`, `frontend/src/routes/admin/+page.svelte` (hub cards become an auto-fill grid, kept as the right-pane content)
- Test: `frontend/tests/e2e/manage-shell.spec.ts` (new)

**Interfaces:**
- Produces in `manage-nav.ts`: `type ManageItem = { href: string; label: string; icon: Component; adminOnly?: boolean }`, `type ManageGroup = { label: string; items: ManageItem[] }`, `manageGroups(isAdmin: boolean): ManageGroup[]`, `isManageRoute(pathname: string): boolean`, `activeManageHref(pathname: string, isAdmin: boolean): string | undefined`. Groups: **Library** (Item types `/settings/item-types`, Relationships `/settings/relationships`, Saved fields `/settings/saved-fields`, Examples `/settings/examples`, Recently deleted `/recently-deleted`), **Account** (Account `/settings/account`), **System** (Status `/status`, then admin-only Users `/admin/users`, Devices `/admin/devices`, Backups `/admin/backups`, Scheduled tasks `/admin/scheduled-tasks`, Admin settings `/admin/settings`). Labels match the current page headings and hub cards.
- Consumes: `desktop` (this task), `auth.isAdmin`, `Page`'s `pageAlign` context (Task 4).

- [ ] **Step 1: Write `manage-nav.test.ts`**: `isManageRoute` is true for `/settings`, `/settings/account`, `/admin`, `/admin/users`, `/recently-deleted`, `/status`, and false for `/`, `/items`, `/items/abc`, `/login`; `manageGroups(false)` has no admin items; `manageGroups(true)` includes the five admin items under System; `activeManageHref('/admin/users/', true)` is `/admin/users`; `activeManageHref('/settings', false)` is `undefined`.
- [ ] **Step 2: Run to see it fail.** Expected: FAIL, module missing.
- [ ] **Step 3: Implement `manage-nav.ts`** to the interface above.
- [ ] **Step 4: Run to see it pass.**
- [ ] **Step 5: Write `manage-shell.spec.ts`** (desktop project, 2048×1152): `the sidebar appears on a settings page` (a `nav` named "Settings sections" with links Item types, Saved fields, Account); `switching sections keeps the sidebar` (click Saved fields, URL changes, sidebar still visible and its entry has `aria-current="page"`); `non-admins do not see admin entries` (use a non-admin fixture user as `users`-related specs do; if none exists, create one through the admin API in the spec); `admins see Users and Backups`; `the sidebar is absent on a narrow viewport` (resize to 800px: no "Settings sections" nav, hub list visible); `the sidebar is absent when signed out` (the `/status` route is reachable signed out today; confirm no sidebar there).
- [ ] **Step 6: Run to see it fail.**
- [ ] **Step 7: Implement `manage-sidebar.svelte`** (a `<nav aria-label="Settings sections">` with group headings and `resolve()`d links, icon plus text, active entry `aria-current="page"`; compact `h-8` rows), and integrate in `+layout.svelte`: when `showNav && desktop.current && isManageRoute(pathname)`, render a two-column container (sidebar `w-56 shrink-0`, sticky; pane `min-w-0 flex-1`) around `{@render children()}` and set the `pageAlign` context to `'start'`; otherwise render children as today. Hub pages keep their link-card content as the pane content on wide screens.
- [ ] **Step 8: Run** the new spec and `poe test-e2e --mode agent tests/e2e/status.spec.ts tests/e2e/admin-settings.spec.ts tests/e2e/admin-devices.spec.ts tests/e2e/recently-deleted.spec.ts`. Expected: PASS.
- [ ] **Step 9: Leave uncommitted.** Suggested message: `feat(frontend): grouped sidebar shell for settings and admin`.

### Task 7: Status dashboard layout

**Files:**
- Modify: `frontend/src/routes/status/+page.svelte:451-840` (layout only; no new data sources)
- Test: `frontend/tests/e2e/status.spec.ts` (extend)

- [ ] **Step 1: Extend `status.spec.ts`** with `the dashboard lays out in columns on a wide screen` (at 2048px the component-group cards are laid out in at least two columns: two group headings have different `x` positions and similar `y`) and `it collapses to one column below lg` (at 900px they share the same `x`).
- [ ] **Step 2: Run to see it fail.**
- [ ] **Step 3: Re-lay the page out** inside `Page width="fluid"`: the overall banner and the existing summary tiles first (build the tile row only from values already on the page; omit any that do not exist), the component-group cards in `lg:grid-cols-2`, and Browser check, Release and Build info in a side column (`lg:grid-cols-[1fr_20rem]` outer grid). Tighten `Card` paddings from `px-5 py-4` to `px-4 py-3`.
- [ ] **Step 4: Run** `poe test-e2e --mode agent tests/e2e/status.spec.ts`. Expected: PASS.
- [ ] **Step 5: Leave uncommitted.** Suggested message: `feat(frontend): dashboard layout for the status page`.

### Task 8: Settings, Admin and table pages onto `Page`

**Files:**
- Modify: `frontend/src/routes/settings/{item-types,relationships,saved-fields,examples,account}/+page.svelte`, `frontend/src/routes/admin/{users,devices,backups,scheduled-tasks,settings}/+page.svelte`, `frontend/src/routes/recently-deleted/+page.svelte`, `frontend/src/lib/components/data-table.svelte`

- [ ] **Step 1: Migrate wrappers** to `Page`: table pages (users, devices, backups, scheduled-tasks, recently-deleted) are `fluid`; item types, relationships, saved fields, account are `reading`; examples and admin settings are `form`. Remove their local `mx-auto flex max-w-…` wrappers and the leftover `h-11` classes if any remain.
- [ ] **Step 2: Tighten `DataTable`** row padding one step (`py-2` rows, `h-8` header) from the `md` breakpoint up only.
- [ ] **Step 3: Run** `poe test-frontend --mode agent`, `poe typecheck-frontend --mode agent`, `poe lint-frontend --mode agent`, then the full e2e suite with `poe test-e2e --mode agent` (expected: all pass; fix selector drift caused by layout, not by changing assertions' intent).
- [ ] **Step 4: Leave uncommitted.** Suggested message: `feat(frontend): fluid settings and admin pages`.

### Task 9: Guidelines, README and final verification

**Files:**
- Modify: `frontend/DESIGN_GUIDELINES.md` (§4, §5, §21), `frontend/README.md` (key patterns: `Page`, `IconButton`, manage shell, `pointer-coarse:`), `docs/superpowers/specs/2026-10-29-compact-wide-ui-design.md` (reading cap becomes 64rem)

- [ ] **Step 1: Update the docs.** §4 states that generous hit areas apply to coarse pointers only; §5 documents the widths (`fluid`/`reading`/`form`/`narrow`), the 2200px ceiling and the manage sidebar; §21 documents the desktop density rule and the icon-only rule (what keeps text); the README names the three components and the `touch-sizes` guard test.
- [ ] **Step 2: Check docs.** Run the repo's markdown formatting and link checks as listed in `CONTRIBUTING.md` for documentation changes.
- [ ] **Step 3: Visual pass** with Chrome DevTools or Playwright screenshots at 360×740 (touch), 1280, 2048 and 2560 for Home, Items, an item, Collections, Settings, Admin → Users and Status, in light and dark. Confirm: labels visible on touch, tooltips on hover, no horizontal scroll, no stretched tiles at 3440.
- [ ] **Step 4: Final gate.** `poe lint-frontend`, `poe typecheck-frontend`, `poe test-frontend`, `poe test-e2e` (all with `--mode agent`). Report any failures with their log paths instead of claiming success.
- [ ] **Step 5: Leave uncommitted.** Suggested message: `docs(frontend): record compact desktop density and width rules`.
