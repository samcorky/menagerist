import { beforeEach, describe, expect, it, vi } from 'vitest';

const { listNodes, listCollections, listNodeTypes } = vi.hoisted(() => ({
	listNodes: vi.fn(),
	listCollections: vi.fn(),
	listNodeTypes: vi.fn()
}));
vi.mock('$lib/api/client', () => ({ listNodes, listCollections, listNodeTypes }));
import {
	ITEM_TYPE_CAP,
	loadItemTypes,
	resetItemTypeCache,
	searchEverything,
	type Results
} from '$lib/palette-sources';

const node = (name: string) => ({ id: name, name });
const coll = (name: string) => ({ id: name, name });
const type = (label: string) => ({ id: label, label, slug: label.toLowerCase() });

function run(query: string, isCurrent = () => true) {
	const updates: Partial<Results>[] = [];
	const done = searchEverything(query, (p) => updates.push(p), isCurrent);
	return { updates, done };
}

function merged(updates: Partial<Results>[]): Partial<Results> {
	return Object.assign({}, ...updates);
}

beforeEach(() => {
	vi.resetAllMocks();
	resetItemTypeCache();
	listNodes.mockResolvedValue({ data: [] });
	listCollections.mockResolvedValue({ data: [] });
	listNodeTypes.mockResolvedValue({ data: [] });
});

describe('searchEverything', () => {
	it('ranks and caps every group', async () => {
		listNodes.mockResolvedValue({
			data: [
				node('xx film 1'),
				node('xx film 2'),
				node('Film'),
				node('Filmography'),
				node('xx film 3'),
				node('Film zzz')
			]
		});
		listCollections.mockResolvedValue({
			data: [coll('xx film 1'), coll('xx film 2'), coll('Film'), coll('Filmography')]
		});
		listNodeTypes.mockResolvedValue({
			data: [type('Short film'), type('Film'), type('Other'), type('Films'), type('Telefilm')]
		});
		const { updates, done } = run('  film ');
		await done;
		const all = merged(updates);
		expect(listNodes).toHaveBeenCalledWith({ query: { q: 'film', limit: 5 } });
		expect(listCollections).toHaveBeenCalledWith({ query: { q: 'film', limit: 3 } });
		expect(all.items).toEqual({
			status: 'ok',
			rows: [
				node('Film'),
				node('Filmography'),
				node('Film zzz'),
				node('xx film 1'),
				node('xx film 2')
			]
		});
		expect(all.collections).toEqual({
			status: 'ok',
			rows: [coll('Film'), coll('Filmography'), coll('xx film 1')]
		});
		expect(all.itemTypes).toEqual({
			status: 'ok',
			rows: [type('Film'), type('Films'), type('Short film')]
		});
		expect(all.pages).toEqual([]);
	});

	it('starts every request without waiting for the others', async () => {
		listNodes.mockReturnValue(new Promise(() => {}));
		void run('film');
		await Promise.resolve();
		expect(listCollections).toHaveBeenCalledTimes(1);
		expect(listNodeTypes).toHaveBeenCalledTimes(1);
	});

	it('drops sources that settle after the search is superseded', async () => {
		const defer = <T>() => {
			let resolve!: (v: T) => void;
			const promise = new Promise<T>((r) => (resolve = r));
			return { promise, resolve };
		};
		const nodes = defer<unknown>();
		const colls = defer<unknown>();
		const types = defer<unknown>();
		listNodes.mockReturnValue(nodes.promise);
		listCollections.mockReturnValue(colls.promise);
		listNodeTypes.mockReturnValue(types.promise);
		let current = true;
		const { updates, done } = run('film', () => current);
		nodes.resolve({ data: [node('Film')] });
		await vi.waitFor(() => expect(updates.length).toBe(2));
		current = false;
		colls.resolve({ data: [coll('Film')] });
		types.resolve({ data: [type('Film')] });
		await done;
		expect(updates).toHaveLength(2);
		expect(updates[0]).toHaveProperty('pages');
		expect(updates[1]).toEqual({ items: { status: 'ok', rows: [node('Film')] } });
	});

	it('shares one in-flight item type request between overlapping searches', async () => {
		listNodeTypes.mockReturnValue(new Promise(() => {}));
		void run('film');
		void run('fil');
		await Promise.resolve();
		expect(listNodeTypes).toHaveBeenCalledTimes(1);
	});

	it('reports pages in the first update', async () => {
		const { updates, done } = run('settings');
		expect(updates[0].pages?.map((p) => p.path)).toContain('/settings');
		await done;
	});

	it('marks only a rejecting source as an error', async () => {
		listCollections.mockRejectedValue(new Error('boom'));
		listNodes.mockResolvedValue({ data: [node('a')] });
		const { updates, done } = run('a');
		await done;
		const all = merged(updates);
		expect(all.collections).toEqual({ status: 'error' });
		expect(all.items).toEqual({ status: 'ok', rows: [node('a')] });
		expect(all.itemTypes?.status).toBe('ok');
	});

	it('treats an error result as a failed source', async () => {
		listNodes.mockResolvedValue({ error: { detail: 'x' } });
		listNodeTypes.mockResolvedValue({});
		const { updates, done } = run('a');
		await done;
		const all = merged(updates);
		expect(all.items).toEqual({ status: 'error' });
		expect(all.itemTypes).toEqual({ status: 'error' });
	});

	it('fetches item types once across searches', async () => {
		listNodeTypes.mockResolvedValue({ data: [type('Film')] });
		await run('film').done;
		await run('fil').done;
		expect(listNodeTypes).toHaveBeenCalledTimes(1);
	});

	it('retries item types after a failure', async () => {
		listNodeTypes.mockRejectedValueOnce(new Error('boom'));
		await run('film').done;
		listNodeTypes.mockResolvedValue({ data: [type('Film')] });
		const { updates, done } = run('film');
		await done;
		expect(listNodeTypes).toHaveBeenCalledTimes(2);
		expect(merged(updates).itemTypes).toEqual({ status: 'ok', rows: [type('Film')] });
	});

	it('retries item types after an error result', async () => {
		listNodeTypes.mockResolvedValueOnce({ error: {} });
		await run('film').done;
		await run('film').done;
		expect(listNodeTypes).toHaveBeenCalledTimes(2);
	});

	it('never updates when no longer current', async () => {
		const { updates, done } = run('film', () => false);
		await done;
		expect(updates).toEqual([]);
	});

	it('makes no requests for a blank query', async () => {
		const { updates, done } = run('   ');
		await done;
		expect(listNodes).not.toHaveBeenCalled();
		expect(listCollections).not.toHaveBeenCalled();
		expect(listNodeTypes).not.toHaveBeenCalled();
		expect(merged(updates)).toEqual({
			items: { status: 'ok', rows: [] },
			collections: { status: 'ok', rows: [] },
			itemTypes: { status: 'ok', rows: [] },
			pages: []
		});
	});

	it('re-runs only the requested sources', async () => {
		listCollections.mockResolvedValue({ data: [coll('Film')] });
		const updates: Partial<Results>[] = [];
		await searchEverything(
			'film',
			(p) => updates.push(p),
			() => true,
			['collections']
		);
		expect(listNodes).not.toHaveBeenCalled();
		expect(listNodeTypes).not.toHaveBeenCalled();
		expect(updates).toEqual([{ collections: { status: 'ok', rows: [coll('Film')] } }]);
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

	it('fails the source on a page 2 error and retries on the next search', async () => {
		listNodeTypes
			.mockResolvedValueOnce({ data: many(0, 100) })
			.mockResolvedValueOnce({ error: { detail: 'x' } });
		const first = run('t');
		await first.done;
		expect(merged(first.updates).itemTypes).toEqual({ status: 'error' });

		listNodeTypes.mockReset();
		listNodeTypes
			.mockResolvedValueOnce({ data: many(0, 100) })
			.mockResolvedValueOnce({ data: many(100, 5) });
		const second = run('t');
		await second.done;
		expect(merged(second.updates).itemTypes).toMatchObject({ status: 'ok' });
		expect(listNodeTypes).toHaveBeenCalledTimes(2);
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
