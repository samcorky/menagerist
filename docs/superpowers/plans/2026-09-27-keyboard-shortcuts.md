# Keyboard Shortcuts and Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Implementation note (superseded in part):** this plan was executed, and the code differs from it in ways that matter. Do **not** reuse the registry code in Task 1 or the root `tinykeys` `$effect` in Task 2: that design froze the app and lost registrations (see "Keyboard shortcuts: one registry, one listener" in `docs/DECISIONS.md`). Other deviations: the help key is `[Shift]+?` and search is `[Shift]+/`; the table e2e test builds a real group field; the rating assertion is "1 star"; e2e runs on ports 8100/5273.

**Goal:** Replace the frontend's scattered, ad hoc `keydown` listeners with one shared shortcut registry, ship a documented global shortcut set (navigation, search, add-item, item actions), a `?` help overlay, and spreadsheet-style arrow-key movement inside table/group fields.

**Architecture:** A new singleton module `frontend/src/lib/shortcuts.svelte.ts` (same pattern as the existing `theme.svelte.ts`/`capture.svelte.ts` controllers) holds a reactive list of shortcut registrations that components add/remove via `$effect`. One root `$effect` in `+layout.svelte` rebuilds a [tinykeys](https://github.com/jamiebuilds/tinykeys) binding map from that list whenever it changes and (re)attaches a single `window`-level listener. A shared input guard (skip firing while the user is typing, unless the registration opts in) replaces the three different copies of that guard that exist today.

**Tech Stack:** Svelte 5 runes, TypeScript strict mode, tinykeys (new dependency), Vitest (unit), Playwright (e2e). Frontend only — no backend changes.

**Spec:** `docs/superpowers/specs/2026-09-27-keyboard-shortcuts-design.md`

## Global Constraints

- Svelte 5 runes throughout (`$state`, `$derived`, `$effect`); no Svelte 4 stores. `shortcuts.svelte.ts` follows the same runes-singleton pattern as `theme.svelte.ts`/`capture.svelte.ts` — confirmed working under this repo's Vitest config (`environment: 'node'`, no jsdom) by a throwaway spike during planning.
- TypeScript strict mode — `poe typecheck-frontend` must pass after every task.
- Every `.svelte` file or `.svelte.ts`/`.svelte.js` module edit or creation must go through the `svelte-file-editor` subagent (CLAUDE.md).
- No SSR — no `+page.server.ts`; everything here is client-side.
- Internal navigation uses `resolve()` from `$app/paths`, never a raw string href.
- Reuse the existing `ResponsiveDialog` component for the help overlay — do not introduce a second dialog primitive.
- British English in all UI copy and comments.
- **Never run `git add` or `git commit`.** Every task ends with the working tree left as-is for the user to review and commit themselves (CLAUDE.md) — the template's usual "Commit" step is replaced with a "Stop for review" step throughout this plan.
- `tinykeys` is a new runtime dependency — per `.github/renovate.json`, runtime `dependencies` updates always require manual review (never auto-merged); no special-casing needed, this is already the repo's default policy.
- Relevant checks for every task in this plan: `poe lint-frontend`, `poe typecheck-frontend`, `poe test-frontend` (or `poe check-changed` for a quick pass). No backend files are touched, so backend checks are never required for this plan.

## Review Focus

- **Duplicate shortcut registrations for the same key** (e.g. two mounted components both claim `/`): the spec doesn't say what happens on a collision. Pinned by Task 1's `buildBindings` test ("the last registration for a duplicate key wins") and by Task 3's route-conditional design, which avoids the collision existing in practice.
- **`?` must not open the help overlay while typing a literal `?` into a text field, but `Cmd/Ctrl+S` must fire while a field has focus** — two opposite-looking policies from the same guard. Pinned by Task 1's `shouldFire`/`buildBindings` tests, which assert both directions explicitly.
- **A `g` key press alone (the user pauses, or presses an unrelated key, before completing `g c`/`g s`/`g e`) must not swallow the keystroke or block normal typing of the letter "g" in a text field afterwards.** Pinned by Task 6's e2e test, which types a word containing "g" into the search box after triggering and abandoning a `g` sequence.
- **The `/` shortcut's cross-page behaviour** (pressed somewhere other than `/items`, it must navigate there and land with the search input focused) is the one shortcut with async, multi-step behaviour the spec describes only at a high level. Pinned by Task 3's e2e-covered navigate-then-focus test.
- **Arrow-key table navigation must not hijack a cell's own native key handling** — a native `<select>` still needs `ArrowUp`/`ArrowDown` to cycle its options, and a text input still needs `ArrowLeft`/`ArrowRight` to move the text cursor when the caret isn't at the field's edge. The spec's "Up/Down/Left/Right move between cells" is silent on this; Task 5 scopes interception to plain text-like `<input>` cells only and pins the caret-edge behaviour with unit tests.

---

## File Structure

| File | Responsibility |
|---|---|
| `frontend/package.json` | Adds the `tinykeys` runtime dependency (Task 1). |
| `frontend/src/lib/shortcuts.svelte.ts` (new) | Core registry: types, `registerShortcut`, `isTypingTarget`, `shouldFire`, `buildBindings`, `formatKeys`, `isMacPlatform`. No DOM listener attachment here — that's wired directly in `+layout.svelte` so the reactive dependency (`shortcutRegistry.active`) is read inside a real Svelte `$effect`. |
| `frontend/tests/shortcuts.test.ts` (new) | Unit tests for the above. |
| `frontend/src/lib/components/shortcuts-help-dialog.svelte` (new) | Renders `shortcutRegistry.active` grouped by `group` inside a `ResponsiveDialog`. |
| `frontend/src/routes/+layout.svelte` (modify) | Root shortcut listener wiring; registers all always-on global shortcuts (`$mod+k`, `n`, `g c`/`g s`/`g e`, `?`, and route-conditional `/`); renders `ShortcutsHelpDialog`. Removes the existing ad hoc Cmd/Ctrl+K block. |
| `frontend/src/routes/items/+page.svelte` (modify) | Registers `/` (focus search) and `Escape` (clear/blur search) via the registry instead of its own `window.addEventListener`. |
| `frontend/src/routes/items/[id]/+page.svelte` (modify) | Registers `e` (enter edit), `Escape` (cancel edit), `Cmd/Ctrl+S` (save) via the registry. |
| `frontend/src/lib/field-types/group/keyboard-nav.ts` (new) | Pure grid-navigation helpers: `shouldMoveCell`, `nextCellPosition`. |
| `frontend/tests/group-keyboard-nav.test.ts` (new) | Unit tests for the above. |
| `frontend/src/lib/field-types/group/GroupInput.svelte` (modify) | Wires arrow-key cell navigation using the helpers above. |
| `frontend/e2e/keyboard-shortcuts.spec.ts` (new) | End-to-end coverage of the full feature set. |

---

## Task 1: Core shortcut registry

**Files:**
- Modify: `frontend/package.json` (add `tinykeys` dependency)
- Create: `frontend/src/lib/shortcuts.svelte.ts`
- Test: `frontend/tests/shortcuts.test.ts`

**Interfaces:**
- Produces: `type ShortcutGroup = 'Global' | 'Search' | 'Add item' | 'Item'`; `type ShortcutDefinition = { id: string; keys: string; description: string; group: ShortcutGroup; allowInInputs?: boolean; handler: (event: KeyboardEvent) => void }`; `shortcutRegistry: { active: ShortcutDefinition[] }`; `registerShortcut(def: ShortcutDefinition): () => void`; `isTypingTarget(target: { tagName?: string; isContentEditable?: boolean } | null | undefined): boolean`; `shouldFire(def: Pick<ShortcutDefinition, 'allowInInputs'>, target: same as above): boolean`; `buildBindings(defs: ShortcutDefinition[]): Record<string, (event: KeyboardEvent) => void>`; `formatKeys(keys: string, isMac: boolean): string`; `isMacPlatform(): boolean`.

- [ ] **Step 1: Add the `tinykeys` dependency**

Run: `cd frontend && npm install tinykeys`

Verify `frontend/package.json` now lists `"tinykeys"` under `"dependencies"`.

- [ ] **Step 2: Write the failing unit test file**

Create `frontend/tests/shortcuts.test.ts`:

```typescript
import { describe, it, expect, vi } from 'vitest';
import {
	shortcutRegistry,
	registerShortcut,
	isTypingTarget,
	shouldFire,
	buildBindings,
	formatKeys
} from '../src/lib/shortcuts.svelte';

describe('isTypingTarget', () => {
	it('is true for INPUT elements', () => {
		expect(isTypingTarget({ tagName: 'INPUT' })).toBe(true);
	});

	it('is true for TEXTAREA elements', () => {
		expect(isTypingTarget({ tagName: 'TEXTAREA' })).toBe(true);
	});

	it('is true for contentEditable elements', () => {
		expect(isTypingTarget({ tagName: 'DIV', isContentEditable: true })).toBe(true);
	});

	it('is false for other elements', () => {
		expect(isTypingTarget({ tagName: 'BUTTON' })).toBe(false);
	});

	it('is false for a null target', () => {
		expect(isTypingTarget(null)).toBe(false);
	});
});

describe('shouldFire', () => {
	it('fires outside inputs by default', () => {
		expect(shouldFire({}, { tagName: 'BUTTON' })).toBe(true);
	});

	it('does not fire inside inputs by default', () => {
		expect(shouldFire({}, { tagName: 'INPUT' })).toBe(false);
	});

	it('fires inside inputs when allowInInputs is set', () => {
		expect(shouldFire({ allowInInputs: true }, { tagName: 'INPUT' })).toBe(true);
	});
});

describe('ShortcutRegistry', () => {
	it('adds a registration to the active list', () => {
		const before = shortcutRegistry.active.length;
		registerShortcut({
			id: 'test-a',
			keys: 'x',
			description: 'Test',
			group: 'Global',
			handler: () => {}
		});
		expect(shortcutRegistry.active.length).toBe(before + 1);
	});

	it('removes a registration when its cleanup function is called', () => {
		const before = shortcutRegistry.active.length;
		const unregister = registerShortcut({
			id: 'test-b',
			keys: 'y',
			description: 'Test',
			group: 'Global',
			handler: () => {}
		});
		expect(shortcutRegistry.active.length).toBe(before + 1);
		unregister();
		expect(shortcutRegistry.active.length).toBe(before);
	});
});

describe('buildBindings', () => {
	it('maps each definition to its key combo', () => {
		const bindings = buildBindings([
			{ id: 'a', keys: 'e', description: 'Edit', group: 'Item', handler: vi.fn() }
		]);
		expect(Object.keys(bindings)).toEqual(['e']);
	});

	it('the last registration for a duplicate key wins', () => {
		const first = vi.fn();
		const second = vi.fn();
		const bindings = buildBindings([
			{ id: 'a', keys: 'e', description: 'First', group: 'Item', handler: first },
			{ id: 'b', keys: 'e', description: 'Second', group: 'Item', handler: second }
		]);
		bindings['e']({ target: { tagName: 'BUTTON' } } as unknown as KeyboardEvent);
		expect(first).not.toHaveBeenCalled();
		expect(second).toHaveBeenCalledOnce();
	});

	it('does not call the handler while typing in an input', () => {
		const guarded = vi.fn();
		const bindings = buildBindings([
			{ id: 'a', keys: 'e', description: 'Guarded', group: 'Item', handler: guarded }
		]);
		bindings['e']({ target: { tagName: 'INPUT' } } as unknown as KeyboardEvent);
		expect(guarded).not.toHaveBeenCalled();
	});

	it('calls the handler while typing in an input when allowInInputs is set', () => {
		const allowed = vi.fn();
		const bindings = buildBindings([
			{
				id: 'b',
				keys: '$mod+s',
				description: 'Save',
				group: 'Item',
				allowInInputs: true,
				handler: allowed
			}
		]);
		bindings['$mod+s']({ target: { tagName: 'INPUT' } } as unknown as KeyboardEvent);
		expect(allowed).toHaveBeenCalledOnce();
	});
});

describe('formatKeys', () => {
	it('renders $mod as a Command glyph on mac', () => {
		expect(formatKeys('$mod+s', true)).toBe('⌘+S');
	});

	it('renders $mod as Ctrl elsewhere', () => {
		expect(formatKeys('$mod+s', false)).toBe('Ctrl+S');
	});

	it('renders Escape as Esc', () => {
		expect(formatKeys('Escape', false)).toBe('Esc');
	});

	it('renders a sequence with "then"', () => {
		expect(formatKeys('g c', false)).toBe('G then C');
	});

	it('renders arrow keys as arrow glyphs', () => {
		expect(formatKeys('ArrowUp', false)).toBe('↑');
	});
});
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd frontend && npx vitest run tests/shortcuts.test.ts`
Expected: FAIL — `../src/lib/shortcuts.svelte` does not exist yet.

- [ ] **Step 4: Write the implementation**

Create `frontend/src/lib/shortcuts.svelte.ts`:

```typescript
export type ShortcutGroup = 'Global' | 'Search' | 'Add item' | 'Item';

export type ShortcutDefinition = {
	id: string;
	/** A tinykeys key combo (`'e'`, `'$mod+s'`) or space-separated sequence (`'g c'`). */
	keys: string;
	description: string;
	group: ShortcutGroup;
	/** Fire even while a text field has focus. Default false. */
	allowInInputs?: boolean;
	handler: (event: KeyboardEvent) => void;
};

type TypingTarget = { tagName?: string; isContentEditable?: boolean } | null | undefined;

/** True when the target is a text-entry element shortcuts should not fire inside by default. */
export function isTypingTarget(target: TypingTarget): boolean {
	if (!target) return false;
	if (target.isContentEditable) return true;
	return target.tagName === 'INPUT' || target.tagName === 'TEXTAREA';
}

/** Whether a registered shortcut should fire for the given event target. */
export function shouldFire(
	def: Pick<ShortcutDefinition, 'allowInInputs'>,
	target: TypingTarget
): boolean {
	if (def.allowInInputs) return true;
	return !isTypingTarget(target);
}

class ShortcutRegistry {
	active = $state<ShortcutDefinition[]>([]);

	register(def: ShortcutDefinition): () => void {
		this.active = [...this.active, def];
		return () => {
			this.active = this.active.filter((d) => d !== def);
		};
	}
}

export const shortcutRegistry = new ShortcutRegistry();

/**
 * Registers a shortcut. Call inside a component's `$effect` and call the
 * returned function from that effect's cleanup, e.g.:
 *
 *   $effect(() => registerShortcut({ ... }));
 */
export function registerShortcut(def: ShortcutDefinition): () => void {
	return shortcutRegistry.register(def);
}

/**
 * Builds a tinykeys binding map from the currently-registered shortcuts,
 * applying the input guard. Pure with respect to its argument, so it's
 * unit-testable without a real `$effect` or DOM listener.
 */
export function buildBindings(
	defs: ShortcutDefinition[]
): Record<string, (event: KeyboardEvent) => void> {
	const bindings: Record<string, (event: KeyboardEvent) => void> = {};
	for (const def of defs) {
		bindings[def.keys] = (event) => {
			if (!shouldFire(def, event.target as TypingTarget)) return;
			def.handler(event);
		};
	}
	return bindings;
}

const KEY_GLYPHS: Record<string, string> = {
	Escape: 'Esc',
	ArrowUp: '↑',
	ArrowDown: '↓',
	ArrowLeft: '←',
	ArrowRight: '→'
};

/** Human-readable rendering of a tinykeys key combo/sequence, for the help overlay. */
export function formatKeys(keys: string, isMac: boolean): string {
	return keys
		.split(' ')
		.map((combo) =>
			combo
				.split('+')
				.map((part) => {
					if (part === '$mod') return isMac ? '⌘' : 'Ctrl';
					if (part in KEY_GLYPHS) return KEY_GLYPHS[part];
					return part.length === 1 ? part.toUpperCase() : part;
				})
				.join('+')
		)
		.join(' then ');
}

const MAC_PLATFORM_RE = /Mac|iPhone|iPod|iPad/;

export function isMacPlatform(): boolean {
	return typeof navigator !== 'undefined' && MAC_PLATFORM_RE.test(navigator.platform ?? '');
}
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd frontend && npx vitest run tests/shortcuts.test.ts`
Expected: PASS, all cases green.

- [ ] **Step 6: Run frontend lint and typecheck**

Run: `cd frontend && npx eslint src/lib/shortcuts.svelte.ts tests/shortcuts.test.ts && npx prettier --check src/lib/shortcuts.svelte.ts tests/shortcuts.test.ts`
Expected: both clean. Fix any reported issues before continuing.

- [ ] **Step 7: Stop for review**

Do not run `git add` or `git commit` — leave the new/modified files in the working tree for the user to review and commit themselves.

---

## Task 2: Root shortcut listener, global shortcuts, and help overlay

**Files:**
- Create: `frontend/src/lib/components/shortcuts-help-dialog.svelte`
- Modify: `frontend/src/routes/+layout.svelte`

**Interfaces:**
- Consumes: `shortcutRegistry`, `registerShortcut`, `buildBindings`, `formatKeys`, `isMacPlatform` from `$lib/shortcuts.svelte` (Task 1); `captureController` from `$lib/capture.svelte.js` (existing); `ResponsiveDialog` from `$lib/components/ui/responsive-dialog/index.js` (existing, see `save-preset-dialog.svelte` for the usage pattern); `resolve` from `$app/paths`; `goto` from `$app/navigation`.
- Produces: `ShortcutsHelpDialog` component, taking `{ open: boolean; onOpenChange: (open: boolean) => void }`, used by `+layout.svelte`.

Every `.svelte` file in this task must be edited via the `svelte-file-editor` subagent, per CLAUDE.md.

- [ ] **Step 1: Create the help overlay component**

Create `frontend/src/lib/components/shortcuts-help-dialog.svelte`:

```svelte
<script lang="ts">
	import * as ResponsiveDialog from '$lib/components/ui/responsive-dialog/index.js';
	import { shortcutRegistry, formatKeys, isMacPlatform, type ShortcutGroup } from '$lib/shortcuts.svelte';

	let { open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void } = $props();

	const GROUP_ORDER: ShortcutGroup[] = ['Global', 'Search', 'Add item', 'Item'];

	let isMac = $derived(isMacPlatform());

	let grouped = $derived(
		GROUP_ORDER.map((group) => ({
			group,
			shortcuts: shortcutRegistry.active.filter((s) => s.group === group)
		})).filter((g) => g.shortcuts.length > 0)
	);
</script>

<ResponsiveDialog.Root {open} {onOpenChange}>
	<ResponsiveDialog.Content title="Keyboard shortcuts" size="md">
		<div class="mt-4 space-y-4">
			{#each grouped as { group, shortcuts } (group)}
				<div class="space-y-1.5">
					<h3 class="text-sm font-medium text-muted-foreground">{group}</h3>
					<ul class="space-y-1">
						{#each shortcuts as shortcut (shortcut.id)}
							<li class="flex items-center justify-between gap-4 text-sm">
								<span>{shortcut.description}</span>
								<kbd
									class="rounded border border-input bg-muted px-1.5 py-0.5 font-mono text-xs"
								>
									{formatKeys(shortcut.keys, isMac)}
								</kbd>
							</li>
						{/each}
					</ul>
				</div>
			{/each}
		</div>
	</ResponsiveDialog.Content>
</ResponsiveDialog.Root>
```

- [ ] **Step 2: Wire the root listener and global shortcuts into the layout**

Modify `frontend/src/routes/+layout.svelte`. Replace the existing keydown `$effect` block (currently lines 49–61, the Cmd/Ctrl+K-only listener) with the shortcut registry wiring, and add the new imports.

Add to the import block:

```typescript
	import { CirclePlus, LayoutGrid, House, Settings, Telescope, BookOpen } from '@lucide/svelte';
	import { tinykeys } from 'tinykeys';
	import { shortcutRegistry, registerShortcut, buildBindings } from '$lib/shortcuts.svelte';
	import ShortcutsHelpDialog from '$lib/components/shortcuts-help-dialog.svelte';
```

Add new state:

```typescript
	let helpOpen = $state(false);
```

Replace the existing:

```typescript
	$effect(() => {
		function handleKeydown(e: KeyboardEvent) {
			const tag = (e.target as HTMLElement).tagName;
			if (tag === 'INPUT' || tag === 'TEXTAREA' || (e.target as HTMLElement).isContentEditable)
				return;
			if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
				e.preventDefault();
				captureController.show();
			}
		}
		window.addEventListener('keydown', handleKeydown);
		return () => window.removeEventListener('keydown', handleKeydown);
	});
```

with:

```typescript
	$effect(() => {
		return registerShortcut({
			id: 'global-quick-capture-mod-k',
			keys: '$mod+k',
			description: 'Quick capture',
			group: 'Add item',
			handler: (e) => {
				e.preventDefault();
				captureController.show();
			}
		});
	});

	$effect(() => {
		return registerShortcut({
			id: 'global-quick-capture-n',
			keys: 'n',
			description: 'Quick capture',
			group: 'Add item',
			handler: () => captureController.show()
		});
	});

	$effect(() => {
		return registerShortcut({
			id: 'global-nav-collection',
			keys: 'g c',
			description: 'Go to Collection',
			group: 'Global',
			handler: () => goto(resolve('/items'))
		});
	});

	$effect(() => {
		return registerShortcut({
			id: 'global-nav-settings',
			keys: 'g s',
			description: 'Go to Settings',
			group: 'Global',
			handler: () => goto(resolve('/settings'))
		});
	});

	$effect(() => {
		return registerShortcut({
			id: 'global-nav-explore',
			keys: 'g e',
			description: 'Go to Explore',
			group: 'Global',
			handler: () => goto(resolve('/explore'))
		});
	});

	$effect(() => {
		return registerShortcut({
			id: 'global-help',
			keys: '?',
			description: 'Show keyboard shortcuts',
			group: 'Global',
			handler: () => (helpOpen = true)
		});
	});

	$effect(() => {
		const bindings = buildBindings(shortcutRegistry.active);
		return tinykeys(window, bindings);
	});
```

Add the dialog to the markup, immediately after the existing `<CaptureSheet />` line:

```svelte
<CaptureSheet />
<ShortcutsHelpDialog open={helpOpen} onOpenChange={(v) => (helpOpen = v)} />
```

- [ ] **Step 3: Manually verify in the dev server**

Run: `poe serve-frontend`

In a browser: press `Cmd/Ctrl+K` — quick capture opens (unchanged from before). Press `n` on a page with no field focused — quick capture opens. Press `g` then `c` — navigates to `/items`. Press `g` then `s` — navigates to `/settings`. Press `g` then `e` — navigates to `/explore`. Press `?` — the help overlay opens listing all four groups' currently-active shortcuts; press `Escape` to close it, focus returns to whatever had it before (standard `ResponsiveDialog` behaviour).

- [ ] **Step 4: Run frontend checks**

Run: `cd frontend && poe check-changed` (or `npx eslint`, `npx prettier --check`, `npx svelte-check`, `npx vitest run` individually if `check-changed` isn't scoped correctly for this diff)
Expected: clean.

- [ ] **Step 5: Stop for review**

Do not run `git add` or `git commit`.

---

## Task 3: Global search shortcut (`/`)

**Files:**
- Modify: `frontend/src/routes/+layout.svelte`
- Modify: `frontend/src/routes/items/+page.svelte`

**Interfaces:**
- Consumes: `registerShortcut` from `$lib/shortcuts.svelte` (Task 1); existing `page` from `$app/state`, `goto`/`resolve`.

- [ ] **Step 1: Register the on-page `/` and `Escape` handlers in `items/+page.svelte`**

Modify `frontend/src/routes/items/+page.svelte`. Replace the existing local listener:

```typescript
	$effect(() => {
		function handleKey(e: KeyboardEvent) {
			if (
				e.key === '/' &&
				document.activeElement?.tagName !== 'INPUT' &&
				document.activeElement?.tagName !== 'TEXTAREA'
			) {
				e.preventDefault();
				searchEl?.focus();
			}
			if (e.key === 'Escape' && document.activeElement === searchEl) {
				searchInput = '';
				searchEl?.blur();
			}
		}
		window.addEventListener('keydown', handleKey);
		return () => window.removeEventListener('keydown', handleKey);
	});
```

with:

```typescript
	import { registerShortcut } from '$lib/shortcuts.svelte';

	$effect(() => {
		return registerShortcut({
			id: 'items-focus-search',
			keys: '/',
			description: 'Focus search',
			group: 'Search',
			handler: (e) => {
				e.preventDefault();
				searchEl?.focus();
			}
		});
	});

	$effect(() => {
		if (document.activeElement !== searchEl) return;
		return registerShortcut({
			id: 'items-clear-search',
			keys: 'Escape',
			description: 'Clear search',
			group: 'Search',
			allowInInputs: true,
			handler: () => {
				searchInput = '';
				searchEl?.blur();
			}
		});
	});
```

(Add the `registerShortcut` import alongside the file's existing `$lib/search-context` import. The `Escape` registration's guard — only registering while `searchEl` is focused — replaces the old handler's own `document.activeElement === searchEl` check, since the registry has no per-event focus-check hook; instead this effect must re-run when focus changes. Reuse the existing `searchEl` `bind:this`/action callback: add `searchEl?.addEventListener('focus', ...)`/`blur` is unnecessary — simplest is to make the effect depend on a new `let searchFocused = $state(false)` toggled by `onfocus`/`onblur` on the search `<Input>`, and have the effect body read `searchFocused` instead of `document.activeElement`.)

Add `let searchFocused = $state(false);` near the other search state, and on the search `<Input>` element add `onfocus={() => (searchFocused = true)}` and `onblur={() => (searchFocused = false)}`. Change the second effect above to:

```typescript
	$effect(() => {
		if (!searchFocused) return;
		return registerShortcut({
			id: 'items-clear-search',
			keys: 'Escape',
			description: 'Clear search',
			group: 'Search',
			allowInInputs: true,
			handler: () => {
				searchInput = '';
				searchEl?.blur();
			}
		});
	});
```

- [ ] **Step 2: Register the cross-page `/` fallback in the layout**

Modify `frontend/src/routes/+layout.svelte`. Add one more shortcut registration, conditional on not already being on `/items` (mirrors the existing `itemsActive` derived value already defined in this file):

```typescript
	$effect(() => {
		if (itemsActive) return;
		return registerShortcut({
			id: 'global-focus-search',
			keys: '/',
			description: 'Focus search',
			group: 'Search',
			handler: (e) => {
				e.preventDefault();
				void goto(`${resolve('/items')}?search=1`);
			}
		});
	});
```

This relies on `routes/items/+page.svelte`'s existing `?search=1` handling (already present, focuses `searchEl` on mount when that query param is set) — no change needed there for the cross-page case. Because this registration is guarded by `if (itemsActive) return`, it is never simultaneously active with the on-page `/` registration from Step 1, so there is no duplicate-key collision in practice (Task 1's `buildBindings` "last wins" behaviour is a defence-in-depth backstop, not something this task relies on).

- [ ] **Step 3: Manually verify in the dev server**

Run: `poe serve-frontend`. From `/settings`, press `/` — navigates to `/items` and focuses the search input. From `/items`, press `/` — focuses the search input directly (no navigation). With the search input focused, press `Escape` — input clears and blurs.

- [ ] **Step 4: Run frontend checks**

Run: `cd frontend && npx eslint src/routes/+layout.svelte src/routes/items/+page.svelte && npx prettier --check src/routes/+layout.svelte src/routes/items/+page.svelte && npx svelte-check && npx vitest run`
Expected: clean, all existing tests still pass.

- [ ] **Step 5: Stop for review**

Do not run `git add` or `git commit`.

---

## Task 4: Item detail shortcuts (`e`, `Esc`, `Cmd/Ctrl+S`)

**Files:**
- Modify: `frontend/src/routes/items/[id]/+page.svelte`

**Interfaces:**
- Consumes: `registerShortcut` from `$lib/shortcuts.svelte` (Task 1); the file's existing `mode` (`$state<'read' | 'edit'>`), `handleSave(event: SubmitEvent)`, `handleCancelEdit()`.

- [ ] **Step 1: Add the shortcut registrations**

Modify `frontend/src/routes/items/[id]/+page.svelte`. Add the import:

```typescript
	import { registerShortcut } from '$lib/shortcuts.svelte';
```

Add a bound reference to the edit form (find the existing `<form class="space-y-4" onsubmit={handleSave}>` around line 549 and add `bind:this={editFormEl}`), plus its declaration near the other `let ... = $state(...)` lines:

```typescript
	let editFormEl = $state<HTMLFormElement | null>(null);
```

Add the three registrations near the other `$effect` blocks:

```typescript
	$effect(() => {
		if (mode !== 'read' || !node) return;
		return registerShortcut({
			id: 'item-edit',
			keys: 'e',
			description: 'Edit item',
			group: 'Item',
			handler: () => (mode = 'edit')
		});
	});

	$effect(() => {
		if (mode !== 'edit') return;
		return registerShortcut({
			id: 'item-cancel-edit',
			keys: 'Escape',
			description: 'Cancel edit',
			group: 'Item',
			handler: () => handleCancelEdit()
		});
	});

	$effect(() => {
		if (mode !== 'edit') return;
		return registerShortcut({
			id: 'item-save',
			keys: '$mod+s',
			description: 'Save item',
			group: 'Item',
			allowInInputs: true,
			handler: (e) => {
				e.preventDefault();
				editFormEl?.requestSubmit();
			}
		});
	});
```

- [ ] **Step 2: Manually verify in the dev server**

Run: `poe serve-frontend`, open an existing item. Press `e` — enters edit mode. Press `Cmd/Ctrl+S` while a field has focus — saves and returns to read mode (same toast/behaviour as clicking the existing Save button). Re-enter edit mode, press `Escape` — cancels, reverting any unsaved changes (same as clicking the existing Cancel button).

- [ ] **Step 3: Run frontend checks**

Run: `cd frontend && npx eslint "src/routes/items/[id]/+page.svelte" && npx prettier --check "src/routes/items/[id]/+page.svelte" && npx svelte-check && npx vitest run`
Expected: clean.

- [ ] **Step 4: Stop for review**

Do not run `git add` or `git commit`.

---

## Task 5: Arrow-key navigation inside table/group fields

**Files:**
- Create: `frontend/src/lib/field-types/group/keyboard-nav.ts`
- Test: `frontend/tests/group-keyboard-nav.test.ts`
- Modify: `frontend/src/lib/field-types/group/GroupInput.svelte`

**Interfaces:**
- Produces: `type ArrowKey = 'ArrowUp' | 'ArrowDown' | 'ArrowLeft' | 'ArrowRight'`; `type CaretInfo = { atStart: boolean; atEnd: boolean }`; `shouldMoveCell(key: ArrowKey, caret: CaretInfo): boolean`; `type GridPosition = { row: number; col: number }`; `nextCellPosition(pos: GridPosition, key: ArrowKey, rowCount: number, colCount: number): GridPosition | null`.

**Scope note (see the spec's Review Focus item on this):** interception is restricted to plain text-like `<input>` cells (the `text`/`number`/`url`/`email`/`phone`/`money`/`quantity` scalar widgets already listed in `GroupInput.svelte`'s own `compactColumnWidth`). Any other focused element inside a cell (a native `<select>` for a `choice` sub-field, the rating radiogroup, a boolean switch, the row's "Remove row" button) is left alone — those widgets already have their own arrow-key semantics (a `<select>` cycles options on Up/Down; `RatingInput.svelte` already uses all four arrows to change its value), and this task must not interfere with them. Movement between those cells stays Tab-only, which is an intentional, narrower scope than "every cell," not an oversight.

- [ ] **Step 1: Write the failing unit test file**

Create `frontend/tests/group-keyboard-nav.test.ts`:

```typescript
import { describe, it, expect } from 'vitest';
import { shouldMoveCell, nextCellPosition } from '../src/lib/field-types/group/keyboard-nav';

describe('shouldMoveCell', () => {
	it('always moves cells on ArrowUp', () => {
		expect(shouldMoveCell('ArrowUp', { atStart: false, atEnd: false })).toBe(true);
	});

	it('always moves cells on ArrowDown', () => {
		expect(shouldMoveCell('ArrowDown', { atStart: false, atEnd: false })).toBe(true);
	});

	it('moves cells on ArrowLeft only when the caret is at the start', () => {
		expect(shouldMoveCell('ArrowLeft', { atStart: true, atEnd: false })).toBe(true);
		expect(shouldMoveCell('ArrowLeft', { atStart: false, atEnd: false })).toBe(false);
	});

	it('moves cells on ArrowRight only when the caret is at the end', () => {
		expect(shouldMoveCell('ArrowRight', { atStart: false, atEnd: true })).toBe(true);
		expect(shouldMoveCell('ArrowRight', { atStart: false, atEnd: false })).toBe(false);
	});
});

describe('nextCellPosition', () => {
	it('moves down within bounds', () => {
		expect(nextCellPosition({ row: 0, col: 0 }, 'ArrowDown', 3, 2)).toEqual({ row: 1, col: 0 });
	});

	it('moves right within bounds', () => {
		expect(nextCellPosition({ row: 0, col: 0 }, 'ArrowRight', 3, 2)).toEqual({ row: 0, col: 1 });
	});

	it('returns null when moving up from the first row', () => {
		expect(nextCellPosition({ row: 0, col: 0 }, 'ArrowUp', 3, 2)).toBeNull();
	});

	it('returns null when moving down from the last row', () => {
		expect(nextCellPosition({ row: 2, col: 0 }, 'ArrowDown', 3, 2)).toBeNull();
	});

	it('returns null when moving left from the first column', () => {
		expect(nextCellPosition({ row: 0, col: 0 }, 'ArrowLeft', 3, 2)).toBeNull();
	});

	it('returns null when moving right from the last column', () => {
		expect(nextCellPosition({ row: 0, col: 1 }, 'ArrowRight', 3, 2)).toBeNull();
	});
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run tests/group-keyboard-nav.test.ts`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Write the implementation**

Create `frontend/src/lib/field-types/group/keyboard-nav.ts`:

```typescript
export type ArrowKey = 'ArrowUp' | 'ArrowDown' | 'ArrowLeft' | 'ArrowRight';

export type CaretInfo = { atStart: boolean; atEnd: boolean };

/**
 * Whether an arrow key press inside a text-like table cell input should move
 * focus to the adjacent cell (true) or be left to move the text cursor
 * (false). Only call this for plain text/number-ish `<input>` elements -
 * selects, buttons, switches and the rating widget keep their own
 * arrow-key behaviour and must never be routed through this check.
 */
export function shouldMoveCell(key: ArrowKey, caret: CaretInfo): boolean {
	if (key === 'ArrowUp' || key === 'ArrowDown') return true;
	return key === 'ArrowLeft' ? caret.atStart : caret.atEnd;
}

export type GridPosition = { row: number; col: number };

const DELTA: Record<ArrowKey, GridPosition> = {
	ArrowUp: { row: -1, col: 0 },
	ArrowDown: { row: 1, col: 0 },
	ArrowLeft: { row: 0, col: -1 },
	ArrowRight: { row: 0, col: 1 }
};

/** The next cell position for a key press, or null if it would move outside the grid. */
export function nextCellPosition(
	pos: GridPosition,
	key: ArrowKey,
	rowCount: number,
	colCount: number
): GridPosition | null {
	const d = DELTA[key];
	const row = pos.row + d.row;
	const col = pos.col + d.col;
	if (row < 0 || row >= rowCount || col < 0 || col >= colCount) return null;
	return { row, col };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npx vitest run tests/group-keyboard-nav.test.ts`
Expected: PASS.

- [ ] **Step 5: Wire the helpers into `GroupInput.svelte`**

Modify `frontend/src/lib/field-types/group/GroupInput.svelte` (via the `svelte-file-editor` subagent). Add the import:

```typescript
	import { shouldMoveCell, nextCellPosition, type ArrowKey } from './keyboard-nav';
```

Add a bound table reference and the handler function, alongside the existing `setCell`/`addRow`/`removeRow` functions:

```typescript
	let tableEl = $state<HTMLTableElement | null>(null);

	function handleCellKeydown(e: KeyboardEvent, ri: number, ci: number) {
		const key = e.key;
		if (key !== 'ArrowUp' && key !== 'ArrowDown' && key !== 'ArrowLeft' && key !== 'ArrowRight')
			return;
		const target = e.target as HTMLInputElement;
		if (target.tagName !== 'INPUT' || target.type === 'checkbox' || target.type === 'radio')
			return;

		const caretPos = target.selectionStart ?? 0;
		const caret = { atStart: caretPos === 0, atEnd: caretPos === target.value.length };
		if (!shouldMoveCell(key as ArrowKey, caret)) return;

		const next = nextCellPosition({ row: ri, col: ci }, key as ArrowKey, rows.length, columns.length);
		if (!next) return;
		e.preventDefault();

		const nextCell = tableEl?.querySelector<HTMLElement>(
			`tbody tr:nth-child(${next.row + 1}) td:nth-child(${next.col + 1})`
		);
		nextCell?.querySelector<HTMLInputElement>('input')?.focus();
	}
```

Update the `<table>` element to bind `tableEl`:

```svelte
<table class="w-full text-sm" bind:this={tableEl}>
```

Update the `{#each columns as [sk, sp] (sk)}` loop inside the row rendering to also track the column index, and wire the new handler onto the cell wrapper `<div>`:

```svelte
{#each rows as row, ri (ri)}
	<tr class="border-b border-input transition-colors last:border-0 hover:bg-muted/30">
		{#each columns as [sk, sp], ci (sk)}
			{@const desc = descriptorForProp(sp)}
			{@const Widget = desc?.InputWidget ?? ScalarInput}
			<td class="px-1 py-0.5 {compactColumnWidth(sp) ?? ''}">
				<div
					class="[&_input]:h-7 [&_input]:border-transparent [&_input]:px-1.5 [&_input]:shadow-none [&_input]:focus-visible:ring-1"
					onkeydown={(e) => handleCellKeydown(e, ri, ci)}
				>
					<Widget
						value={row[sk] ?? ''}
						onChange={(v) => setCell(ri, sk, v)}
						ariaLabel={sp.title || sk}
						prop={sp}
					/>
				</div>
			</td>
		{/each}
		<td class="px-1 py-0.5 text-right">
			<Button type="button" variant="ghost" class="size-7" onclick={() => removeRow(ri)} aria-label="Remove row">
				<X class="size-4" />
			</Button>
		</td>
	</tr>
{/each}
```

- [ ] **Step 6: Manually verify in the dev server**

Run: `poe serve-frontend`. On an item type with a table/group field with at least two text columns and two rows, focus a cell's input, press ArrowDown/Up/Left/Right at various caret positions and confirm: Up/Down always move a row; Left/Right only move a column when the caret is already at that edge of the text, otherwise the cursor moves within the text as normal.

- [ ] **Step 7: Run frontend checks**

Run: `cd frontend && npx eslint src/lib/field-types/group/keyboard-nav.ts src/lib/field-types/group/GroupInput.svelte tests/group-keyboard-nav.test.ts && npx prettier --check src/lib/field-types/group/keyboard-nav.ts src/lib/field-types/group/GroupInput.svelte tests/group-keyboard-nav.test.ts && npx svelte-check && npx vitest run`
Expected: clean, no regressions in `group-columns.test.ts` or any other existing group-field test.

- [ ] **Step 8: Stop for review**

Do not run `git add` or `git commit`.

---

## Task 6: End-to-end coverage

**Files:**
- Create: `frontend/e2e/keyboard-shortcuts.spec.ts`

**Interfaces:**
- Consumes: `createItem`, `createItemType`, `addFieldToItemType`, `uniqueName` from `./helpers` (existing, see `frontend/e2e/helpers.ts`).

- [ ] **Step 1: Write the e2e spec**

Create `frontend/e2e/keyboard-shortcuts.spec.ts`:

```typescript
import { test, expect } from '@playwright/test';
import { createItem, createItemType, addFieldToItemType, uniqueName } from './helpers';

test('g c / g s / g e navigate between the main sections', async ({ page }) => {
	await page.goto('/');
	await expect(page.getByRole('link', { name: 'Home' })).toBeVisible();

	await page.keyboard.press('g');
	await page.keyboard.press('c');
	await expect(page).toHaveURL(/\/items$/);

	await page.keyboard.press('g');
	await page.keyboard.press('s');
	await expect(page).toHaveURL(/\/settings$/);

	await page.keyboard.press('g');
	await page.keyboard.press('e');
	await expect(page).toHaveURL(/\/explore$/);
});

test('an abandoned g-sequence does not block typing a literal "g"', async ({ page }) => {
	await page.goto('/items');
	await page.keyboard.press('g');
	// Pause past any sequence-reset window, then type into the search box.
	await page.waitForTimeout(1200);
	const search = page.getByPlaceholder('Search your items…');
	await search.fill('vintage gramophone');
	await expect(search).toHaveValue('vintage gramophone');
});

test('/ focuses search on the items page, and navigates there from elsewhere', async ({ page }) => {
	await page.goto('/items');
	await page.keyboard.press('/');
	await expect(page.getByPlaceholder('Search your items…')).toBeFocused();

	await page.goto('/settings');
	await page.keyboard.press('/');
	await expect(page).toHaveURL(/\/items\?search=1$|\/items$/);
	await expect(page.getByPlaceholder('Search your items…')).toBeFocused();
});

test('? opens the shortcuts help overlay', async ({ page }) => {
	await page.goto('/');
	await page.keyboard.press('?');
	const dialog = page.getByRole('dialog', { name: 'Keyboard shortcuts' });
	await expect(dialog).toBeVisible();
	await expect(dialog.getByText('Quick capture').first()).toBeVisible();
	await page.keyboard.press('Escape');
	await expect(dialog).toBeHidden();
});

test('e / Esc / Cmd+S drive edit mode on an item', async ({ page }) => {
	const name = uniqueName('Shortcut item');
	await createItem(page, { name });

	await page.keyboard.press('e');
	const nameInput = page.getByLabel('Name');
	await expect(nameInput).toBeVisible();

	await nameInput.fill(`${name} (edited, then cancelled)`);
	await page.keyboard.press('Escape');
	await expect(page.getByText(name, { exact: true }).first()).toBeVisible();

	await page.keyboard.press('e');
	await page.getByLabel('Name').fill(`${name} (saved)`);
	await page.keyboard.press('Control+s');
	await expect(page.getByText('Saved')).toBeVisible();
	await expect(page.getByText(`${name} (saved)`, { exact: true }).first()).toBeVisible();
});

test('arrow keys move between text cells in a table field, without breaking mid-text cursor movement', async ({
	page
}) => {
	const typeName = uniqueName('Shortcut table type');
	await createItemType(page, { label: typeName, fields: [{ label: 'Column A' }] });
	await addFieldToItemType(page, { label: 'Column B' });

	const itemName = uniqueName('Shortcut table item');
	await createItem(page, { name: itemName, type: typeName });

	await page.keyboard.press('e');
	await page.getByRole('button', { name: 'Add row' }).click();
	await page.getByRole('button', { name: 'Add row' }).click();

	const firstCellFirstRow = page.locator('table tbody tr').nth(0).locator('td').nth(0).locator('input');
	const secondCellFirstRow = page.locator('table tbody tr').nth(0).locator('td').nth(1).locator('input');
	const firstCellSecondRow = page.locator('table tbody tr').nth(1).locator('td').nth(0).locator('input');

	await firstCellFirstRow.fill('hello');
	await firstCellFirstRow.press('Home');
	// Caret at start: ArrowLeft moves the cursor, not the cell (no-op here, nothing to the left).
	await firstCellFirstRow.press('ArrowLeft');
	await expect(firstCellFirstRow).toBeFocused();
	// Caret at start, ArrowRight moves the cursor within the text (not a cell move).
	await firstCellFirstRow.press('ArrowRight');
	await expect(firstCellFirstRow).toBeFocused();

	await firstCellFirstRow.press('End');
	// Caret at end: ArrowRight moves to the next cell.
	await firstCellFirstRow.press('ArrowRight');
	await expect(secondCellFirstRow).toBeFocused();

	// ArrowDown always moves a row, regardless of caret position.
	await secondCellFirstRow.press('Home');
	await secondCellFirstRow.press('ArrowDown');
	await expect(page.locator('table tbody tr').nth(1).locator('td').nth(1).locator('input')).toBeFocused();

	await firstCellFirstRow.focus();
	await firstCellFirstRow.press('ArrowDown');
	await expect(firstCellSecondRow).toBeFocused();
});

test('Enter submits the edit form from a single-line text field, and the rating widget stays keyboard-operable', async ({
	page
}) => {
	const typeName = uniqueName('Shortcut audit type');
	await createItemType(page, { label: typeName, fields: [{ label: 'Condition', kind: 'rating' }] });

	const itemName = uniqueName('Shortcut audit item');
	await createItem(page, { name: itemName, type: typeName });

	await page.keyboard.press('e');
	const nameInput = page.getByLabel('Name');
	await nameInput.fill(`${itemName} (via Enter)`);
	await nameInput.press('Enter');
	await expect(page.getByText('Saved')).toBeVisible();
	await expect(page.getByText(`${itemName} (via Enter)`, { exact: true }).first()).toBeVisible();

	// Tab order audit: the rating widget (§16a "Rating") must be keyboard-reachable
	// and operable without a mouse - not just present in the DOM.
	await page.keyboard.press('e');
	await page.getByRole('radiogroup', { name: 'Condition' }).locator('[role="radio"]').first().focus();
	await page.keyboard.press('ArrowRight');
	await expect(page.getByRole('radio', { name: '2 stars' })).toHaveAttribute('aria-checked', 'true');
});
```

- [ ] **Step 2: Run the new e2e spec**

Run: `cd frontend && poe test-e2e-headed -- keyboard-shortcuts` (or the plain `poe test-e2e -- keyboard-shortcuts` variant; see `CONTRIBUTING.md`'s "End-to-end tests" section for the exact invocation and required `compose.verify.yaml` setup this repo's e2e suite depends on).
Expected: all seven tests pass. If the `?`-overlay test's dialog `name` doesn't match, check `ShortcutsHelpDialog`'s `ResponsiveDialog.Content title` prop matches exactly (`"Keyboard shortcuts"`). If the rating-widget assertion fails, re-check `RatingInput.svelte`'s existing `role="radiogroup"`/`role="radio"` structure hasn't changed since this plan was written (see the file as read during planning) rather than assuming this task's changes broke it — this task does not touch `RatingInput.svelte`.

- [ ] **Step 3: Run the full existing e2e suite once, to catch any regression**

Run: `cd frontend && poe test-e2e`
Expected: no regressions in `connect-items.spec.ts`, `create-item.spec.ts`, `field-types.spec.ts`, `manage-item-types.spec.ts`, `quick-capture.spec.ts`, or `set-item-type.spec.ts` — in particular `quick-capture.spec.ts`'s `openQuickCapture` helper (which presses `Control+k`) must still pass unchanged, confirming Task 2's migration preserved the existing quick-capture behaviour exactly.

- [ ] **Step 4: Stop for review**

Do not run `git add` or `git commit`.

---

## Final check

After all six tasks: run `poe lint-frontend`, `poe typecheck-frontend`, `poe test-frontend`, and the full `poe test-e2e` once more from a clean state, then hand the (uncommitted) working tree to the user for review.
