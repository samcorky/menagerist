# Compact, wide, icon-led desktop UI

> Decisions 3 (icon-only header navigation) and 4 (Settings-only sidebar) are superseded by `2026-10-29-app-shell-and-settings-flows-design.md`: navigation is now one collapsible app sidebar and search is a field in the top bar.

Date: 2026-10-29. Status: draft for approval.

## Intent

On a desktop monitor the UI feels bloated and airy, and it leaves most of the screen unused. The shadcn style is already `rhea` (compact), and the `Button` primitive is already compact (`h-8`), so the bloat is mostly local overrides and layout caps, not the theme:

- About 139 uses of `h-11`, `min-h-11` or `size-11` force 44px touch-size controls on every device.
- The header and most pages are capped at `max-w-4xl` (896px), so on a 2048px viewport roughly 45% of the width is used.
- Header, toolbar and row actions carry text labels that a tooltip could supply.

The aim is a calm, compact desktop UI that fills the screen, while phones and tablets keep their current touch comfort. This matches the existing intent of `DESIGN_GUIDELINES.md` §21 ("compact… avoid oversized headings/buttons").

## Goals

- Desktop (mouse/trackpad) controls, gaps and padding one step tighter, with the 44px target preserved on touch.
- Content that uses the available width where wide content helps (grids, tables, Explore, collection view, Settings, Admin, Status).
- Icon-only buttons with tooltips for navigation, toolbars and row actions.
- Every screen covered, user-facing screens first.

## Non-goals

- No change to colours, fonts, radius tokens, dark mode or the mobile layout (bottom nav, compact header).
- No new navigation destinations and no new terminology; §24 still applies.
- No backend or API changes.

## Anti-goals

- Desktop must not become cramped or hard to hit; compact does not mean sub-28px controls.
- Touch users (the Android capture flow in particular) must not lose their 44px targets or visible labels.
- An icon-only button must never lose its accessible name. Removing a visible label without an `aria-label` and a tooltip is a failure.
- Wide lines of body text, forms and item detail must not stretch to the full viewport.

## Target viewports

Design for a 2048px-wide viewport (a 2560×1440 monitor at 125% scaling). It must also work at 2560px (100%) and at 1280px, and ultrawide screens must not stretch tiles. Below the `lg` breakpoint (1024px) layouts collapse to today's single-column behaviour.

## Decisions

### 1. Density only for precise pointers

Compact sizing is the default for desktop; touch sizing is opted into with Tailwind's `pointer-coarse:` variant (the `pointer-fine:`/`pointer-coarse:` variants need Tailwind v4.1 or later; the builder should confirm the installed version). The existing `h-11` overrides become either the shared touch treatment or are removed where the primitive's default is enough. Compact targets: controls 28–32px (`h-7`/`h-8`), page padding one step down, section gaps `gap-3`/`gap-4` instead of looser values. Icon buttons keep the invisible hit-slop already in `button.svelte`.

### 2. Width

- Shell: header and `#main-scroll` content use the full viewport width with `px-4` gutters. The `max-w-4xl` in `+layout.svelte:193` goes.
- Fluid pages (collection/Items grid, Collections, Explore, tables, Status, Settings, Admin): no cap; grids use `repeat(auto-fill, minmax(Npx, 1fr))` so the column count follows the width, instead of a fixed count. Roughly 8 columns at 1080p and 10–11 at 1440p are expected, tuned in the browser.
- Reading pages are capped by type: item detail, account and list-style settings pages at 64rem (`max-w-5xl`); forms (new item, examples, admin settings) at 48rem (`max-w-3xl`); login/setup stay at `max-w-sm`. Inside the Settings/Admin shell they are left-aligned next to the sidebar. (Changed from the first draft's 72–80rem, which was wider than any of these pages is today.)
- Hard ceiling for the whole app at about 2200px, centred. *This is my call*; revisit if you routinely use ultrawide.

### 3. Icon-only buttons and tooltips

- Icon-only: header navigation (Home, Items, Collections, Search, Settings, API docs, theme), toolbar and filter/sort controls, row and card actions.
- Keep text: buttons that commit or cancel a decision (Save, Cancel, Delete, Sign in), and the single primary call to action on an empty state. The header's primary "New item" action becomes a filled icon button on desktop; its mobile equivalent is unchanged.
- Every icon-only button has an `aria-label` and a tooltip carrying the same text (and the keyboard shortcut where one exists).
- Hover and focus use the existing `ui/tooltip`. Use `ui/popover-tooltip` where the content is more than a few words or needs to work on touch. The header search button may become a wider "Search… ⌘K"-style field; builder's call.
- Accessible names must stay stable, because the e2e suite and the `DataTable` rule in design §5 rely on them.

### 4. Settings and Admin

Replace the single stack of link cards with a shared two-column shell from `lg` up: a persistent left list of sections and the selected page on the right. Below `lg`, Settings keeps today's hub list and Admin keeps its hub. Sections are grouped:

- **Library:** Item types, Relationships, Saved fields, Examples, Recently deleted.
- **Account:** Account (profile, devices).
- **System:** Status. Admins also see Users, Devices, Backups, Scheduled tasks and Admin settings.

*Assumption:* Admin sections join the same sidebar under the System group instead of a second sidebar. Existing URLs do not change. The sidebar highlights the active route. Pages with wide content (tables) use the full right-hand area; form-like pages cap themselves per decision 2.

### 5. Status page

Keep the existing groups and cards. Re-lay them out from `lg` up as a dashboard: an overall banner and a row of summary tiles on top (for example item count, media size, jobs, last backup, workers, version, only where the data already exists on the page), the component-health groups in a two-column grid, and Browser check, Release and Build info in a narrow side column. No new data sources.

### 6. Documentation

Update `DESIGN_GUIDELINES.md` §4 ("generous hit areas" becomes touch-only), §5 (width and shell rules), §21 (density tokens), and the frontend README's relevant section, so the rules are recorded where agents will find them.

## Constraints

- Follow `AGENTS.md`: Svelte 5 runes, `resolve()` for hrefs, shadcn-svelte/bits-ui primitives, British English, no `git add`/`git commit` by the agent.
- Frontend changes must pass `poe typecheck-frontend`, `poe lint-frontend` and unit tests, and the e2e specs must be updated for any changed accessible names or layouts.
- Keep changes in staged, reviewable pieces (see order below).

## Order of work

1. Foundation: `Button`/input density variants, header and layout shell, width rules, tooltip wiring for icon buttons.
2. User-facing screens: Home, Items, Collections, collection view, item detail, new item/capture, Search, Explore.
3. Settings and Admin shell, Status dashboard, the data tables.
4. Guideline and README updates, e2e and unit-test fixes, a browser check at 1280, 2048 and 2560px plus a phone-sized viewport.

## Left to the builder

- Exact compact token values, grid minimum tile widths and reading-page cap widths, tuned by looking at the running app.
- Which individual buttons count as "toolbar/row actions" and go icon-only, following the rule in decision 3.
- Whether the shared touch treatment is a `Button` size variant, a utility class, or a CSS custom property.
