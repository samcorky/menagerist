import { afterEach, describe, expect, it, vi } from 'vitest';

const { listExampleEntities } = vi.hoisted(() => ({ listExampleEntities: vi.fn() }));
vi.mock('$lib/api/client', () => ({ listExampleEntities }));
import {
	describeCounts,
	describeRemoval,
	dismissExamplesBanner,
	groupKept,
	invalidateExampleIds,
	isExamplesBannerDismissed,
	loadExampleIds,
	readExampleFilter,
	visibleItems,
	writeExampleFilter,
	reasonLabel
} from '$lib/examples';

const zero = { presets: 0, relationship_types: 0, item_types: 0, items: 0, connections: 0 };

describe('describeCounts', () => {
	it('lists non-zero parts and omits zeros', () => {
		expect(describeCounts({ ...zero, item_types: 3, items: 14 })).toBe('3 item types, 14 items');
	});
	it('uses singular for one', () => {
		expect(describeCounts({ ...zero, items: 1, connections: 2 })).toBe('1 item, 2 connections');
	});
	it('is empty for all zeros', () => {
		expect(describeCounts(zero)).toBe('');
	});
});

describe('reasonLabel', () => {
	it('maps known reasons', () => {
		expect(reasonLabel('edited')).toBe('you edited them');
		expect(reasonLabel('has your connections or files')).toBe(
			'they have your connections or files'
		);
		expect(reasonLabel('still in use')).toBe('they are still in use');
	});
	it('falls back for unknown reasons', () => {
		expect(reasonLabel('mystery')).toBe('they are no longer just examples');
	});
});

describe('groupKept', () => {
	it('groups by reason in first-seen order', () => {
		const kept = ['edited', 'still in use', 'edited'].map((reason) => ({
			kind: 'item',
			label: 'x',
			reason
		}));
		expect(groupKept(kept)).toEqual([
			{ reason: 'edited', count: 2 },
			{ reason: 'still in use', count: 1 }
		]);
	});
});

describe('describeRemoval', () => {
	it('gives one sentence when nothing was kept', () => {
		expect(describeRemoval({ pack_id: 'music', removed: { ...zero, items: 17 }, kept: [] })).toBe(
			'Removed 17 items.'
		);
	});
	it('names what was kept and why', () => {
		const kept = [
			{ kind: 'item', label: 'a', reason: 'edited' },
			{ kind: 'item', label: 'b', reason: 'edited' },
			{ kind: 'item', label: 'c', reason: 'still in use' }
		];
		expect(describeRemoval({ pack_id: 'music', removed: { ...zero, items: 5 }, kept })).toBe(
			'Removed 5 items. 2 items were kept because you edited them; 1 item was kept because they are still in use.'
		);
	});
	it('handles nothing removed', () => {
		expect(describeRemoval({ pack_id: 'music', removed: zero, kept: [] })).toBe(
			'Nothing needed removing.'
		);
	});
});

describe('examples banner dismissal', () => {
	afterEach(() => vi.unstubAllGlobals());
	it('starts not dismissed and remembers dismissal', () => {
		const store = new Map<string, string>();
		vi.stubGlobal('localStorage', {
			getItem: (key: string) => store.get(key) ?? null,
			setItem: (key: string, value: string) => store.set(key, value)
		});
		expect(isExamplesBannerDismissed()).toBe(false);
		dismissExamplesBanner();
		expect(isExamplesBannerDismissed()).toBe(true);
	});
	it('does not throw when storage throws', () => {
		vi.stubGlobal('localStorage', {
			getItem: () => {
				throw new Error('blocked');
			},
			setItem: () => {
				throw new Error('blocked');
			}
		});
		expect(isExamplesBannerDismissed()).toBe(false);
		expect(() => dismissExamplesBanner()).not.toThrow();
	});
});

function stubStorage(initial: Record<string, string> = {}): void {
	const store = new Map(Object.entries(initial));
	vi.stubGlobal('localStorage', {
		getItem: (key: string) => store.get(key) ?? null,
		setItem: (key: string, value: string) => store.set(key, value)
	});
}

describe('example filter preference', () => {
	afterEach(() => vi.unstubAllGlobals());
	it('defaults to all and remembers the choice', () => {
		stubStorage();
		expect(readExampleFilter()).toBe('all');
		writeExampleFilter('only');
		expect(readExampleFilter()).toBe('only');
		writeExampleFilter('hide');
		expect(readExampleFilter()).toBe('hide');
	});
	it('honours the older hide flag until a choice is saved', () => {
		stubStorage({ 'menagerist.examples.hide': 'true' });
		expect(readExampleFilter()).toBe('hide');
		writeExampleFilter('all');
		expect(readExampleFilter()).toBe('all');
	});
	it('falls back to all for an unknown saved value', () => {
		stubStorage({ 'menagerist.examples.filter': 'nonsense' });
		expect(readExampleFilter()).toBe('all');
	});
	it('does not throw when storage throws', () => {
		vi.stubGlobal('localStorage', {
			getItem: () => {
				throw new Error('blocked');
			},
			setItem: () => {
				throw new Error('blocked');
			}
		});
		expect(readExampleFilter()).toBe('all');
		expect(() => writeExampleFilter('hide')).not.toThrow();
	});
});

describe('visibleItems', () => {
	const items = [{ id: 'a' }, { id: 'b' }];
	const examples = new Set(['a']);
	it('filters by the chosen mode', () => {
		expect(visibleItems(items, examples, 'all')).toEqual(items);
		expect(visibleItems(items, examples, 'hide')).toEqual([{ id: 'b' }]);
		expect(visibleItems(items, examples, 'only')).toEqual([{ id: 'a' }]);
	});
});

describe('loadExampleIds', () => {
	afterEach(() => {
		invalidateExampleIds();
		listExampleEntities.mockReset();
	});
	it('loads once, then serves the cache until invalidated', async () => {
		listExampleEntities.mockResolvedValue({ data: { item_ids: ['a'], item_type_ids: ['t'] } });
		const first = await loadExampleIds();
		await loadExampleIds();
		expect(first.items.has('a')).toBe(true);
		expect(first.itemTypes.has('t')).toBe(true);
		expect(listExampleEntities).toHaveBeenCalledTimes(1);
		invalidateExampleIds();
		await loadExampleIds();
		expect(listExampleEntities).toHaveBeenCalledTimes(2);
	});
	it('is empty when the lookup fails', async () => {
		listExampleEntities.mockRejectedValue(new Error('down'));
		expect((await loadExampleIds()).items.size).toBe(0);
	});
	it('is empty when the response has no data', async () => {
		listExampleEntities.mockResolvedValue({ error: { detail: 'x' } });
		expect((await loadExampleIds()).items.size).toBe(0);
	});
});
