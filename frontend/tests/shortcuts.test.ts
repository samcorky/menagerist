import { describe, it, expect, vi } from 'vitest';
import {
	shortcutRegistry,
	registerShortcut,
	isTypingTarget,
	isInsideOverlay,
	shouldFire,
	buildBindings,
	formatKeys,
	attachShortcuts
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

	it('is true for SELECT elements', () => {
		expect(isTypingTarget({ tagName: 'SELECT' })).toBe(true);
	});
});

describe('overlay guard', () => {
	it('does not fire for a target inside an overlay', () => {
		expect(shouldFire({}, { tagName: 'BUTTON', closest: () => ({}) })).toBe(false);
	});

	it('fires when the target is not inside an overlay', () => {
		expect(shouldFire({}, { tagName: 'BUTTON', closest: () => null })).toBe(true);
	});

	it('fires inside an overlay when allowInInputs is set', () => {
		expect(shouldFire({ allowInInputs: true }, { tagName: 'BUTTON', closest: () => ({}) })).toBe(
			true
		);
	});

	it('isInsideOverlay queries the overlay roles', () => {
		const closest = vi.fn(() => ({}));
		expect(isInsideOverlay({ closest })).toBe(true);
		expect(closest).toHaveBeenCalledWith(
			'[role="dialog"],[role="alertdialog"],[role="listbox"],[role="menu"]'
		);
		expect(isInsideOverlay(null)).toBe(false);
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

	it('drops optional-modifier parts', () => {
		expect(formatKeys('[Shift]+?', false)).toBe('?');
		expect(formatKeys('[Shift]+/', false)).toBe('/');
	});
});

describe('attachShortcuts', () => {
	type Listener = (event: unknown) => void;

	function makeTarget() {
		const state: { listener?: Listener } = {};
		const target = {
			addEventListener: (_type: string, l: Listener) => {
				state.listener = l;
			},
			removeEventListener: vi.fn()
		};
		return { state, target };
	}

	function press(state: { listener?: Listener }, key: string) {
		state.listener?.({
			key,
			code: /^[a-z]$/.test(key) ? `Key${key.toUpperCase()}` : key,
			getModifierState: () => false,
			repeat: false,
			isComposing: false,
			target: { tagName: 'BODY' }
		});
	}

	function def(keys: string, handler: () => void) {
		return { id: keys, keys, description: keys, group: 'Global' as const, handler };
	}

	it('fires a shortcut registered after attaching', () => {
		const { state, target } = makeTarget();
		const detach = attachShortcuts(target);
		const handler = vi.fn();
		const off = registerShortcut(def('x', handler));
		press(state, 'x');
		expect(handler).toHaveBeenCalledTimes(1);
		off();
		detach();
	});

	it('picks up a shortcut registered after an earlier key press', () => {
		const { state, target } = makeTarget();
		const detach = attachShortcuts(target);
		const a = vi.fn();
		const b = vi.fn();
		const offA = registerShortcut(def('x', a));
		press(state, 'x');
		expect(a).toHaveBeenCalledTimes(1);
		const offB = registerShortcut(def('y', b));
		press(state, 'y');
		expect(b).toHaveBeenCalledTimes(1);
		offA();
		offB();
		detach();
	});

	it('stops firing after unregistering', () => {
		const { state, target } = makeTarget();
		const detach = attachShortcuts(target);
		const handler = vi.fn();
		const off = registerShortcut(def('x', handler));
		off();
		press(state, 'x');
		expect(handler).not.toHaveBeenCalled();
		detach();
	});

	it('fires a two-key sequence', () => {
		const { state, target } = makeTarget();
		const detach = attachShortcuts(target);
		const handler = vi.fn();
		const off = registerShortcut(def('g c', handler));
		press(state, 'g');
		press(state, 'c');
		expect(handler).toHaveBeenCalledTimes(1);
		off();
		detach();
	});

	it('ignores events whose default was prevented', () => {
		const { state, target } = makeTarget();
		const detach = attachShortcuts(target);
		const handler = vi.fn();
		const off = registerShortcut(def('x', handler));
		const base = {
			key: 'x',
			code: 'KeyX',
			getModifierState: () => false,
			repeat: false,
			isComposing: false,
			target: { tagName: 'BODY' }
		};
		state.listener?.({ ...base, defaultPrevented: true });
		expect(handler).not.toHaveBeenCalled();
		state.listener?.({ ...base, defaultPrevented: false });
		expect(handler).toHaveBeenCalledTimes(1);
		off();
		detach();
	});

	it('removes the same keydown listener on detach', () => {
		const { state, target } = makeTarget();
		const detach = attachShortcuts(target);
		detach();
		expect(target.removeEventListener).toHaveBeenCalledWith('keydown', state.listener);
	});
});
