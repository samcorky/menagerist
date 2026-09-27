# Keyboard shortcuts and navigation

**Status:** approved design, ready for implementation planning.
**Scope:** frontend only. No backend changes.
**Reviewed with:** Sam Cork, 2026-09-27.

## Problem

Keyboard handling in the frontend today is scattered across independent, uncoordinated `window.addEventListener('keydown', …)` blocks:

- `routes/+layout.svelte` — `Cmd/Ctrl+K` opens quick capture.
- `routes/items/+page.svelte` — `/` focuses the search input (only works while already on `/items`), `Escape` clears/blurs it.
- Assorted per-component key handling: `RatingInput.svelte`, `ChoiceExtras.svelte`, `GroupExtras.svelte`, `tags-input.svelte`, `capture-sheet.svelte`, `file-drop.svelte`, `media-gallery.svelte`.

Each of the first two reimplements its own "don't fire while the user is typing in a field" guard, slightly differently. There is no shared registry, no discoverability (no shortcut list anywhere), and no cross-page consistency (`/` doesn't work outside `/items`).

Separately, `DESIGN_GUIDELINES.md` §20a mandates deliberate focus management after actions but says nothing about keyboard-only completeness inside complex widgets (table/group fields, the schema editor), and no dedicated audit of that has been done.

This spec covers both: a real global shortcut system, and closing the known keyboard-completeness gaps.

## Goals

1. One shared shortcut registry, replacing the ad hoc listeners above, with a single consistent input-guard policy.
2. A documented, discoverable shortcut set covering global navigation, item actions, add-item, and search — see the inventory below.
3. A `?` help overlay that lists whatever shortcuts are actually active on the current screen (not a hand-maintained static page).
4. Keyboard-only completeness fixes for form/field navigation: tab order audit, Enter-to-save, and spreadsheet-style arrow-key movement inside table/group fields.

## Non-goals

- No line-by-line ARIA re-audit of every component (separate concern, not this spec).
- No `j/k` vim-style list navigation (declined — arrow keys only, and even that was deferred: see the shortcut inventory).
- No per-user customisable key bindings.
- No changes to any backend module.

## Architecture

A new singleton module, `frontend/src/lib/shortcuts.svelte.ts`, following the existing pattern of `theme.svelte.ts` and `capture.svelte.ts` (the two sanctioned non-rune singletons per `AGENTS.md`'s "Svelte 5 runes throughout" rule).

**`ShortcutRegistry` class:**

- Holds a reactive (`$state`) list of active registrations: `{ id, keys, description, group, allowInInputs?, handler }`.
- `keys` is either a single combo string (`'e'`, `'Escape'`, `'$mod+s'`, `'/'`, `'?'`) or a space-separated sequence (`'g c'`) for chords.
- Components call `registerShortcut(def)` inside an `$effect`; the effect's own cleanup calls the returned unregister function. This means the active set the registry holds is always exactly what's bindable on the current page/dialog — which is also the data source for the help overlay, so the two can never drift apart.
- `group` is the display heading in the help overlay (`'Global'`, `'Item'`, `'Add item'`, `'Search'`).

**Dispatch:**

- One root `keydown` listener, attached once in `routes/+layout.svelte`, replacing the Cmd/Ctrl+K block currently there.
- Single-key and modifier combos are matched directly against the registry.
- Sequences (only `g c` / `g s` / `g e` for now) are handled by wrapping **tinykeys** (new dependency, see below) internally; the tinykeys instance is recreated whenever the set of registered sequence shortcuts changes.
- **Input guard**, applied once centrally instead of three times independently: a shortcut does not fire while `document.activeElement` is an `INPUT`, `TEXTAREA`, or `isContentEditable`, unless its registration sets `allowInInputs: true`. `Escape` and `Cmd/Ctrl+S` opt in; everything else does not.

**Dependency: tinykeys**

Reasoning: chord-sequence matching (correct reset timing when the user pauses or presses an unrelated key between `g` and `c`) is fiddly to hand-roll correctly, and tinykeys is ~600 bytes gzipped with zero dependencies of its own — it is used *only* inside `shortcuts.svelte.ts`, not spread through components. Approved by the user in the brainstorming session. It's a runtime dependency, so per `.github/renovate.json` it gets grouped under "frontend dependencies" but is never auto-merged (manual review required for all `dependencies`-type updates), which is the existing policy and needs no special-casing.

**Migration:** the existing ad hoc listeners (layout's Cmd+K, items page's `/` and `Escape`) are migrated onto the registry rather than left standing alongside it — otherwise there would be two competing systems answering the same keys.

## Shortcut inventory

| Group | Shortcut | Action | Notes |
|---|---|---|---|
| Global | `g` `c` | Go to Collection (`/items`) | tinykeys sequence |
| Global | `g` `s` | Go to Settings (`/settings`) | tinykeys sequence |
| Global | `g` `e` | Go to Explore (`/explore`) | tinykeys sequence |
| Search | `/` | Focus search | Global (not `/items`-only as today). If not already on `/items`, navigate there with `?search=1` (the route already supports this param — see `routes/items/+page.svelte`), then focus once loaded. |
| Global | `Cmd/Ctrl+K` | Quick capture | Existing behaviour, migrated onto the registry unchanged. |
| Global | `?` | Open shortcuts help overlay | Guarded by the input policy like everything else. |
| Add item | `n` | Quick capture | Same as `Cmd/Ctrl+K` (`captureController.show()`) — a second mnemonic for the same action, not the desktop header's "New item" button, which navigates to the separate full `/items/new` form. Those two existing entry points already diverge (mobile bottom nav opens quick capture; desktop header button goes to the full form) — this spec doesn't change that, it just gives quick capture a letter mnemonic alongside its existing chord. |
| Item | `e` | Enter edit mode | Registered only while viewing an item that isn't already in edit mode. |
| Item | `Esc` | Cancel edit | Registered only while editing. Existing narrower `Escape` behaviours (search-box clear, dialog close) remain their own separately-scoped registrations and keep working. |
| Item | `Cmd/Ctrl+S` | Save | `allowInInputs: true` — must fire while a field has focus; must call `preventDefault()` to stop the browser's native Save dialog. |

Form/field navigation (tab order, Enter-to-save, arrow-key table movement) is behavioural, not a new binding — see below.

## Help overlay

A shadcn-svelte `Dialog`, opened by `?`, rendering the registry's current active set grouped by `group`, each row showing its description and key combo as `<kbd>` chips. Standard dialog focus-trap and return-focus-to-trigger behaviour per `DESIGN_GUIDELINES.md` §20a — no new focus-management logic needed beyond what the `Dialog` component already provides. No separate entry point elsewhere in the UI for v1; discoverability is the `?` convention itself.

## Form/field keyboard-completeness audit

Scoped to known, concrete gaps — not a speculative full rewrite:

1. **Tab order audit** across the item edit form, the schema editor, and open dialogs, looking for mouse-only interactive elements (e.g. schema editor drag handles). `RatingInput.svelte` is believed to already have keyboard support per its WI-5 implementation notes — verify, don't assume, during implementation.
2. **Enter-to-save** on single-line inputs (text, number, url, email, phone, money): confirm native `<input>`-inside-`<form>` Enter-submits behaviour isn't being suppressed anywhere by a leftover `preventDefault`.
3. **Arrow-key movement inside table/group fields**: in `GroupInput.svelte`, Up/Down/Left/Right move focus between cells spreadsheet-style, instead of relying solely on Tab across many small cells. This is the one genuinely new interaction in this section.

Explicitly out of scope: a full ARIA re-audit (separate concern; the `accessibility-specialist` agent covers that ground, not this spec).

## Testing

- **Unit (Vitest):** `shortcuts.svelte.ts` — registration/unregistration lifecycle, input-guard behaviour (including the `allowInInputs` opt-out), sequence dispatch via tinykeys, help-overlay data derivation.
- **Playwright e2e:** one new spec exercising `/` (including cross-page navigate-then-focus), `g c`/`g s`/`g e`, `?` overlay open/close, `e`/`Esc`/`Cmd+S` on an item, and arrow-key movement inside a table field.
- No backend tests — no backend changes.

## Rollout

Single frontend-only body of work. No feature flag, no phased rollout — this ships as one coherent change once implemented and reviewed, per the normal `poe check-changed` / `poe lint-frontend` / `poe typecheck-frontend` / `poe test-frontend` gate.
