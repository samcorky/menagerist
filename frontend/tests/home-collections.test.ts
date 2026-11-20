import { beforeEach, describe, expect, it, vi } from 'vitest';

const { prefs, offline } = vi.hoisted(() => ({
	prefs: { values: {} as Record<string, unknown>, save: vi.fn() },
	offline: { offline: false }
}));
vi.mock('$lib/preferences.svelte', () => ({
	OFFLINE_PREFERENCES: 'offline reason',
	preferences: { value: (key: string) => prefs.values[key], save: prefs.save }
}));
vi.mock('$lib/offline.svelte', () => ({ offlineController: offline }));

import {
	HOME_FULL,
	MAX_HOME_COLLECTIONS,
	chosenCollections,
	homeCollectionIds,
	homeCollectionQuery,
	homeToggleBlocked,
	toggleHomeCollection
} from '$lib/home-collections';

beforeEach(() => {
	prefs.values = {};
	prefs.save.mockReset().mockResolvedValue({ ok: true });
	offline.offline = false;
});

describe('collections chosen for Home', () => {
	it("reads the person's setting, empty until it is known", () => {
		expect(homeCollectionIds()).toEqual([]);
		prefs.values['home.collections'] = ['a', 'b'];
		expect(homeCollectionIds()).toEqual(['a', 'b']);
	});

	it('adds a collection last and takes it off again, saving the whole list', async () => {
		prefs.values['home.collections'] = ['a'];

		await toggleHomeCollection('b');
		expect(prefs.save).toHaveBeenLastCalledWith('home.collections', ['a', 'b']);

		await toggleHomeCollection('a');
		expect(prefs.save).toHaveBeenLastCalledWith('home.collections', []);
	});

	it("passes on the store's answer, so a failed save is reported", async () => {
		prefs.save.mockResolvedValue({ ok: false, message: 'Could not save' });

		expect(await toggleHomeCollection('a')).toEqual({ ok: false, message: 'Could not save' });
	});

	it('is refused offline, with the reason, without saving', async () => {
		offline.offline = true;

		expect(homeToggleBlocked('a')).toBe('offline reason');
		expect(await toggleHomeCollection('a')).toEqual({ ok: false, message: 'offline reason' });
		expect(prefs.save).not.toHaveBeenCalled();
	});

	it('refuses another collection when Home is full, but still takes one off', async () => {
		const full = Array.from({ length: MAX_HOME_COLLECTIONS }, (_, i) => `id-${i}`);
		prefs.values['home.collections'] = full;

		expect(homeToggleBlocked('another')).toBe(HOME_FULL);
		expect(await toggleHomeCollection('another')).toEqual({ ok: false, message: HOME_FULL });
		expect(homeToggleBlocked('id-0')).toBeNull();
		await toggleHomeCollection('id-0');
		expect(prefs.save).toHaveBeenLastCalledWith('home.collections', full.slice(1));
	});

	it('keeps the chosen order and skips collections that no longer exist', () => {
		const shelves = [{ id: 'a' }, { id: 'b' }, { id: 'c' }];
		expect(chosenCollections(['c', 'gone', 'a'], shelves)).toEqual([{ id: 'c' }, { id: 'a' }]);
	});

	it('asks for the newest items of the collection, whatever its kind', () => {
		expect(homeCollectionQuery('a')).toEqual({
			v: 1,
			where: { op: 'and', children: [{ kind: 'collection', mode: 'any', in: ['a'] }] },
			sort: [{ by: 'created', dir: 'desc' }]
		});
	});
});
