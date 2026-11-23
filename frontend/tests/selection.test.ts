import { describe, expect, it } from 'vitest';
import { SELECTION_LIMIT, Selection } from '../src/lib/selection.svelte';

const ids = (n: number, from = 0) => Array.from({ length: n }, (_, i) => `id-${from + i}`);

describe('Selection', () => {
	it('enters and exits, and exit forgets every pick', () => {
		const s = new Selection();
		s.enter();
		s.toggle('a');
		expect(s.active).toBe(true);
		s.exit();
		expect(s.active).toBe(false);
		expect(s.count).toBe(0);
	});

	it('toggles an item on and off', () => {
		const s = new Selection();
		s.toggle('a');
		expect(s.has('a')).toBe(true);
		s.toggle('a');
		expect(s.has('a')).toBe(false);
	});

	it('takes at most the limit and refuses a pick beyond it', () => {
		const s = new Selection();
		s.selectAll(ids(SELECTION_LIMIT + 50));
		expect(s.count).toBe(SELECTION_LIMIT);
		expect(s.atLimit).toBe(true);
		s.toggle('extra');
		expect(s.has('extra')).toBe(false);
		s.toggle('id-0');
		expect(s.atLimit).toBe(false);
	});

	it('counts picks the current view hides', () => {
		const s = new Selection();
		s.selectAll(['a', 'b', 'c']);
		expect(s.hiddenCount(['a'])).toBe(2);
		expect(s.hiddenCount(['a', 'b', 'c', 'd'])).toBe(0);
	});

	it('select all and deselect all touch only the visible items', () => {
		const s = new Selection();
		s.toggle('hidden');
		s.selectAll(['a', 'b']);
		expect(s.count).toBe(3);
		s.deselectAll(['a', 'b']);
		expect([...s.ids]).toEqual(['hidden']);
	});

	it('drops the named items and clears while staying in selection mode', () => {
		const s = new Selection();
		s.enter();
		s.selectAll(['a', 'b', 'c']);
		s.drop(['a', 'zzz']);
		expect([...s.ids]).toEqual(['b', 'c']);
		s.clear();
		expect(s.count).toBe(0);
		expect(s.active).toBe(true);
	});
});
