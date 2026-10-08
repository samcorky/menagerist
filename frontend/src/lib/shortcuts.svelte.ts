import { createKeybindingsHandler } from 'tinykeys';

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

type TypingTarget =
	| { tagName?: string; isContentEditable?: boolean; closest?: (selector: string) => unknown }
	| null
	| undefined;

/** True when the target is a text-entry element shortcuts should not fire inside by default. */
export function isTypingTarget(target: TypingTarget): boolean {
	if (!target) return false;
	if (target.isContentEditable) return true;
	return target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT';
}

const OVERLAY_SELECTOR = '[role="dialog"],[role="alertdialog"],[role="listbox"],[role="menu"]';

/** True when the target sits inside a dialog, listbox or menu. */
export function isInsideOverlay(target: TypingTarget): boolean {
	return Boolean(target?.closest?.(OVERLAY_SELECTOR));
}

/** Whether a registered shortcut should fire for the given event target. */
export function shouldFire(
	def: Pick<ShortcutDefinition, 'allowInInputs'>,
	target: TypingTarget
): boolean {
	if (def.allowInInputs) return true;
	return !isTypingTarget(target) && !isInsideOverlay(target);
}

class ShortcutRegistry {
	// Plain source of truth. Reading reactive state inside effect cleanups can be
	// stale within a flush, so a read-modify-write on `active` loses updates.
	#defs: ShortcutDefinition[] = [];

	/** Write-only published snapshot of `#defs` for reactive consumers (e.g. the help dialog). */
	active = $state.raw<ShortcutDefinition[]>([]);

	/** Non-reactive current list; safe to read anywhere, including key handlers. */
	get current(): ShortcutDefinition[] {
		return this.#defs;
	}

	register(def: ShortcutDefinition): () => void {
		this.#defs = [...this.#defs, def];
		this.active = this.#defs;
		return () => {
			this.#defs = this.#defs.filter((d) => d !== def);
			this.active = this.#defs;
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

/**
 * Attaches one long-lived keydown listener that reads the registry at
 * key-press time, so it never depends on effect ordering and keeps tinykeys'
 * sequence state between presses. Bindings are rebuilt only when the
 * registry's list identity changes. The custom `ignore` is needed because
 * tinykeys' default ignores all form-element events, defeating `allowInInputs`.
 */
export function attachShortcuts(
	target: Pick<Window, 'addEventListener' | 'removeEventListener'>
): () => void {
	let cachedFor: ShortcutDefinition[] | undefined;
	let handler: ((event: KeyboardEvent) => void) | undefined;
	let matched = false;
	const listener = (event: KeyboardEvent) => {
		if (event.defaultPrevented) return;
		const defs = shortcutRegistry.current;
		if (!handler || defs !== cachedFor) {
			cachedFor = defs;
			const bindings = buildBindings(defs);
			for (const keys of Object.keys(bindings)) {
				const inner = bindings[keys];
				bindings[keys] = (e) => {
					matched = true;
					inner(e);
				};
			}
			handler = createKeybindingsHandler(bindings, {
				ignore: (e) => e.repeat || e.isComposing
			});
		}
		handler(event);
		// tinykeys stops at the first completed binding and leaves the rest of its pending
		// sequences half-matched (a stale `g e` swallows the next `g`), so start afresh.
		if (matched) {
			matched = false;
			handler = undefined;
		}
	};
	target.addEventListener('keydown', listener);
	return () => target.removeEventListener('keydown', listener);
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
				.filter((part) => !/^\[.+\]$/.test(part))
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
