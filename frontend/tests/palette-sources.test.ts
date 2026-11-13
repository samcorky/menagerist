import { beforeEach, describe, expect, it, vi } from 'vitest';

const { listNodeTypes, searchApi } = vi.hoisted(() => ({
	listNodeTypes: vi.fn(),
	searchApi: vi.fn()
}));
vi.mock('$lib/api/client', () => ({ listNodeTypes, searchEverything: searchApi }));
import {
	ITEM_TYPE_CAP,
	loadItemTypes,
	resetItemTypeCache,
	searchEverything,
	type Results,
	type SearchScope
} from '$lib/palette-sources';
import { paletteLayout } from '$lib/palette-search';

const hit = (kind: string, title: string, score = 80) => ({ kind, ref: title, title, score });
const type = (label: string) => ({ id: label, label, slug: label.toLowerCase() });
const scopeFor = (path: string): SearchScope => ({ layout: paletteLayout(path) });

function run(query: string, only?: Parameters<typeof searchEverything>[3], path = '/') {
	const updates: Partial<Results>[] = [];
	const done = searchEverything(
		query,
		(p) => updates.push(p),
		() => true,
		only,
		scopeFor(path)
	);
	return { updates, done };
}

function merged(updates: Partial<Results>[]): Partial<Results> {
	return Object.assign({}, ...updates);
}

beforeEach(() => {
	vi.resetAllMocks();
	resetItemTypeCache();
	listNodeTypes.mockResolvedValue({ data: [] });
	searchApi.mockResolvedValue({ data: { results: [], failed: [] } });
});

describe('searchEverything', () => {
	it('asks the server once and sorts its rows into groups, capped per group', async () => {
		searchApi.mockResolvedValue({
			data: {
				results: [
					...Array.from({ length: 7 }, (_, n) => hit('item', `Film ${n}`)),
					hit('collection', 'Films'),
					hit('item_type', 'Film'),
					hit('setting', 'Backups to keep'),
					hit('scheduled_task', 'Nightly backup')
				],
				failed: []
			}
		});
		const { updates, done } = run('  film ');
		await done;
		expect(searchApi).toHaveBeenCalledTimes(1);
		expect(searchApi).toHaveBeenCalledWith({ query: { q: 'film', limit: 5 } });
		const all = merged(updates);
		expect(all.items).toMatchObject({ status: 'ok' });
		expect((all.items as { rows: unknown[] }).rows).toHaveLength(5);
		expect(all.collections).toEqual({ status: 'ok', rows: [hit('collection', 'Films')] });
		expect(all.itemTypes).toEqual({ status: 'ok', rows: [hit('item_type', 'Film')] });
		expect(all.settings).toEqual({ status: 'ok', rows: [hit('setting', 'Backups to keep')] });
		expect(all.tasks).toEqual({ status: 'ok', rows: [hit('scheduled_task', 'Nightly backup')] });
	});

	it('reports pages straight away, before the server has answered', async () => {
		searchApi.mockReturnValue(new Promise(() => {}));
		const { updates } = run('settings');
		await Promise.resolve();
		expect(updates[0].pages?.map((p) => p.path)).toContain('/settings');
		expect(updates.some((u) => 'items' in u)).toBe(false);
	});

	it('marks only a kind the server could not search as an error', async () => {
		searchApi.mockResolvedValue({
			data: { results: [hit('item', 'Film')], failed: ['collection'] }
		});
		const { updates, done } = run('film');
		await done;
		const all = merged(updates);
		expect(all.collections).toEqual({ status: 'error' });
		expect(all.items).toMatchObject({ status: 'ok' });
	});

	it('marks every server group as an error when the request fails', async () => {
		searchApi.mockResolvedValue({ error: {} });
		const { updates, done } = run('film');
		await done;
		const all = merged(updates);
		for (const key of ['items', 'collections', 'itemTypes', 'settings', 'tasks'] as const) {
			expect(all[key]).toEqual({ status: 'error' });
		}
		searchApi.mockRejectedValue(new Error('offline'));
		const again = run('film');
		await again.done;
		expect(merged(again.updates).items).toEqual({ status: 'error' });
	});

	it('re-asks only for the requested groups', async () => {
		searchApi.mockResolvedValue({ data: { results: [hit('collection', 'Films')], failed: [] } });
		const { updates, done } = run('film', ['collections']);
		await done;
		expect(Object.keys(merged(updates)).sort()).toEqual(['collections']);
		expect(searchApi).toHaveBeenCalledWith({ query: { q: 'film', limit: 3 } });
	});

	it('asks for as many as the largest group on this page needs', async () => {
		await run('film', undefined, '/settings/server').done;
		expect(searchApi).toHaveBeenCalledWith({ query: { q: 'film', limit: 7 } });
	});

	it('drops answers that arrive after the search is superseded', async () => {
		let current = true;
		const updates: Partial<Results>[] = [];
		searchApi.mockImplementation(async () => {
			current = false;
			return { data: { results: [hit('item', 'Film')], failed: [] } };
		});
		await searchEverything(
			'film',
			(p) => updates.push(p),
			() => current
		);
		expect(updates.some((u) => 'items' in u)).toBe(false);
	});

	it('makes no requests for a blank query', async () => {
		const { updates, done } = run('   ');
		await done;
		expect(searchApi).not.toHaveBeenCalled();
		const all = merged(updates);
		expect(all.pages).toEqual([]);
		expect(all.settings).toEqual({ status: 'ok', rows: [] });
		expect(all.collectionItems).toEqual({ status: 'ok', rows: [] });
	});
});

describe('the collection in view', () => {
	const member = (title: string) => ({ ...hit('item', title), in_collection: true });

	it('is sent to the server, which marks its items; they show in their own group', async () => {
		searchApi.mockResolvedValue({
			data: { results: [member('Film'), hit('item', 'Film b'), member('xx film')], failed: [] }
		});
		const { updates, done } = run('film', undefined, '/collections/my-films');
		await done;
		expect(searchApi).toHaveBeenCalledTimes(1);
		expect(searchApi).toHaveBeenCalledWith({
			query: { q: 'film', limit: 13, collection: 'my-films' }
		});
		const all = merged(updates);
		expect(all.collectionItems).toEqual({
			status: 'ok',
			rows: [member('Film'), member('xx film')]
		});
		expect(all.items).toEqual({ status: 'ok', rows: [hit('item', 'Film b')] });
	});

	it('is left out of the request elsewhere', async () => {
		const { updates, done } = run('film');
		await done;
		expect(searchApi).toHaveBeenCalledWith({ query: { q: 'film', limit: 5 } });
		expect(merged(updates).collectionItems).toEqual({ status: 'ok', rows: [] });
	});

	it('fails with the items it came with', async () => {
		searchApi.mockResolvedValue({ data: { results: [], failed: ['item'] } });
		const { updates, done } = run('film', undefined, '/collections/my-films');
		await done;
		expect(merged(updates).collectionItems).toEqual({ status: 'error' });
		expect(merged(updates).items).toEqual({ status: 'error' });
	});

	it('is refreshed by retrying the collection items alone', async () => {
		searchApi.mockResolvedValue({ data: { results: [member('Film')], failed: [] } });
		const { updates, done } = run('film', ['collectionItems'], '/collections/my-films');
		await done;
		expect(Object.keys(merged(updates)).sort()).toEqual(['collectionItems', 'items']);
	});
});

describe('loadItemTypes', () => {
	it('fetches item types once across calls', async () => {
		listNodeTypes.mockResolvedValue({ data: [type('Film')] });
		await loadItemTypes();
		await loadItemTypes();
		expect(listNodeTypes).toHaveBeenCalledTimes(1);
	});

	it('retries after a failure and after an error result', async () => {
		listNodeTypes.mockRejectedValueOnce(new Error('boom'));
		await expect(loadItemTypes()).rejects.toThrow();
		listNodeTypes.mockResolvedValueOnce({ error: {} });
		await expect(loadItemTypes()).rejects.toThrow();
		listNodeTypes.mockResolvedValue({ data: [type('Film')] });
		await expect(loadItemTypes()).resolves.toEqual([type('Film')]);
		expect(listNodeTypes).toHaveBeenCalledTimes(3);
	});
});

describe('loadItemTypes paging', () => {
	const many = (from: number, n: number) =>
		Array.from({ length: n }, (_, i) => ({
			id: `t${from + i}`,
			label: `T${from + i}`,
			slug: `t${from + i}`
		}));

	it('pages through the after cursor until a short page', async () => {
		listNodeTypes
			.mockResolvedValueOnce({ data: many(0, 100) })
			.mockResolvedValueOnce({ data: many(100, 100) })
			.mockResolvedValueOnce({ data: many(200, 50) });
		const all = await loadItemTypes();
		expect(all).toHaveLength(250);
		expect(listNodeTypes).toHaveBeenCalledTimes(3);
		expect(listNodeTypes).toHaveBeenNthCalledWith(1, { query: { limit: 100 } });
		expect(listNodeTypes).toHaveBeenNthCalledWith(2, { query: { limit: 100, after: 't99' } });
		expect(listNodeTypes).toHaveBeenNthCalledWith(3, { query: { limit: 100, after: 't199' } });
		await loadItemTypes();
		expect(listNodeTypes).toHaveBeenCalledTimes(3);
	});

	it('fails on a page 2 error and loads again on the next call', async () => {
		listNodeTypes
			.mockResolvedValueOnce({ data: many(0, 100) })
			.mockResolvedValueOnce({ error: { detail: 'x' } });
		await expect(loadItemTypes()).rejects.toThrow();

		listNodeTypes.mockReset();
		listNodeTypes
			.mockResolvedValueOnce({ data: many(0, 100) })
			.mockResolvedValueOnce({ data: many(100, 5) });
		await expect(loadItemTypes()).resolves.toHaveLength(105);
		expect(listNodeTypes).toHaveBeenCalledTimes(2);
	});

	it('shares one in-flight request between overlapping calls', async () => {
		listNodeTypes.mockReturnValue(new Promise(() => {}));
		void loadItemTypes();
		void loadItemTypes();
		await Promise.resolve();
		expect(listNodeTypes).toHaveBeenCalledTimes(1);
	});

	it('stops at the safety cap', async () => {
		let next = 0;
		listNodeTypes.mockImplementation(async ({ query }: { query: { limit: number } }) => {
			const data = many(next, query.limit);
			next += query.limit;
			return { data };
		});
		const all = await loadItemTypes();
		expect(all).toHaveLength(ITEM_TYPE_CAP);
		expect(listNodeTypes).toHaveBeenCalledTimes(ITEM_TYPE_CAP / 100);
	});
});
