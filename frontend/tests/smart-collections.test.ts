import { beforeEach, describe, expect, it, vi } from 'vitest';

const { createCollection, updateCollection, searchNodes } = vi.hoisted(() => ({
	createCollection: vi.fn(),
	updateCollection: vi.fn(),
	searchNodes: vi.fn()
}));
vi.mock('$lib/api/client', () => ({ createCollection, updateCollection, searchNodes }));

import {
	SmartCollectionError,
	countLabel,
	describeCollectionCount,
	describeSaveError,
	isSmart,
	manualCollections,
	loadSmartCollection,
	saveSmartCollection,
	smartCollectionSummary,
	updateDefinition
} from '$lib/smart-collections';
import type { Query } from '$lib/query/types';

const query: Query = {
	v: 1,
	where: { op: 'and', children: [{ kind: 'favourite', value: true }] },
	sort: [{ by: 'name', dir: 'asc' }]
};
const lookup = { typeLabel: (s: string) => s, fieldLabel: (_t: string, k: string) => k };
const collection = (over: Record<string, unknown> = {}) =>
	({
		id: 'c1',
		name: 'Faves',
		kind: 'dynamic',
		definition: query,
		item_count: 2,
		item_count_capped: false,
		warnings: [],
		...over
	}) as never;

beforeEach(() => vi.resetAllMocks());

async function failure(promise: Promise<unknown>): Promise<SmartCollectionError> {
	try {
		await promise;
	} catch (e) {
		expect(e).toBeInstanceOf(SmartCollectionError);
		return e as SmartCollectionError;
	}
	throw new Error('expected a rejection');
}

describe('saveSmartCollection', () => {
	it('creates with the definition and returns the collection', async () => {
		createCollection.mockResolvedValue({ data: { id: 'c1' } });
		expect(await saveSmartCollection('  Faves ', query)).toEqual({ id: 'c1' });
		expect(createCollection).toHaveBeenCalledWith({ body: { name: 'Faves', definition: query } });
	});

	it('surfaces a 400 with its path and message', async () => {
		createCollection.mockResolvedValue({
			error: { detail: 'where.children[1]: That value is not valid' },
			response: { status: 400 }
		});
		const e = await failure(saveSmartCollection('Faves', query));
		expect(e.status).toBe(400);
		expect(e.path).toBe('where.children[1]');
		expect(e.target).toEqual({ where: [1] });
		expect(e.message).toBe('That value is not valid');
	});

	it('keeps a 400 without a path as a plain message', async () => {
		createCollection.mockResolvedValue({
			error: { detail: 'Name is required' },
			response: { status: 400 }
		});
		const e = await failure(saveSmartCollection('', query));
		expect(e.path).toBeNull();
		expect(e.message).toBe('Name is required');
	});

	it('does not leak server text for a 500', async () => {
		createCollection.mockResolvedValue({ error: { detail: 'boom' }, response: { status: 500 } });
		const e = await failure(saveSmartCollection('Faves', query));
		expect(e.status).toBe(500);
		expect(e.path).toBeNull();
		expect(e.message).toBe("Couldn't save the smart collection. Try again.");
	});

	it('reports offline and a thrown request as no status', async () => {
		createCollection.mockResolvedValueOnce({ error: {} });
		expect((await failure(saveSmartCollection('x', query))).status).toBeNull();
		createCollection.mockRejectedValueOnce(new Error('offline'));
		expect((await failure(saveSmartCollection('x', query))).status).toBeNull();
	});

	it('treats a response with no data as a failure', async () => {
		createCollection.mockResolvedValue({ response: { status: 200 } });
		expect((await failure(saveSmartCollection('x', query))).status).toBe(200);
	});
});

describe('updateDefinition', () => {
	it('patches the definition', async () => {
		updateCollection.mockResolvedValue({ data: { id: 'c1' } });
		expect(await updateDefinition('c1', query)).toEqual({ id: 'c1' });
		expect(updateCollection).toHaveBeenCalledWith({
			path: { collection_id: 'c1' },
			body: { definition: query }
		});
	});

	it('surfaces a 409 and a 400 with a sort path', async () => {
		updateCollection.mockResolvedValueOnce({ error: { detail: 'x' }, response: { status: 409 } });
		expect((await failure(updateDefinition('c1', query))).status).toBe(409);
		updateCollection.mockResolvedValueOnce({
			error: { detail: 'sort[0]: Unknown field' },
			response: { status: 400 }
		});
		const e = await failure(updateDefinition('c1', query));
		expect(e.target).toEqual({ sort: 0 });
	});
});

describe('isSmart', () => {
	it('is true only for the dynamic kind', () => {
		expect(isSmart(collection())).toBe(true);
		expect(isSmart(collection({ kind: 'manual', definition: null }))).toBe(false);
	});
});

describe('countLabel', () => {
	it.each([
		[0, false, '0'],
		[12, false, '12'],
		[1000, true, '1,000+'],
		[1234, false, '1,234']
	])('%s capped=%s', (count, capped, expected) => {
		expect(countLabel(count, capped)).toBe(expected);
	});
});

describe('smartCollectionSummary', () => {
	it('gives the same chip texts as the builder', () => {
		const summary = smartCollectionSummary(query, lookup);
		expect(summary?.lead).toBeNull();
		expect(summary?.chips.map((c) => c.text)).toEqual(['Is a favourite']);
	});

	it('marks chips the server warned about', () => {
		const summary = smartCollectionSummary(query, lookup, [
			{ path: 'where.children[0]', message: 'gone' }
		]);
		expect(summary?.chips[0].warning).toBe(true);
	});

	it('is null for a definition the decoder rejects', () => {
		expect(smartCollectionSummary({ v: 2 }, lookup)).toBeNull();
		expect(smartCollectionSummary(null, lookup)).toBeNull();
	});
});

describe('loadSmartCollection', () => {
	const page = (over: Record<string, unknown> = {}) => ({
		data: {
			items: [{ id: 'n1' }],
			total: 1,
			total_capped: false,
			next_cursor: null,
			warnings: [],
			...over
		}
	});

	it('runs the saved query with its sort and returns the page', async () => {
		searchNodes.mockResolvedValue(page({ next_cursor: 'abc' }));
		const result = await loadSmartCollection(collection(), { cursor: 'prev', limit: 10 });
		expect(searchNodes).toHaveBeenCalledWith({ body: { query, limit: 10, cursor: 'prev' } });
		expect(result).toEqual({
			query,
			items: [{ id: 'n1' }],
			total: 1,
			totalCapped: false,
			nextCursor: 'abc',
			warnings: []
		});
	});

	it('merges server and search warnings without duplicates', async () => {
		searchNodes.mockResolvedValue(
			page({
				warnings: [
					{ path: 'where.children[0]', message: 'gone' },
					{ path: 'sort[0]', message: 'no sort' }
				]
			})
		);
		const result = await loadSmartCollection(
			collection({ warnings: [{ path: 'where.children[0]', message: 'gone' }] }),
			{}
		);
		expect(result.warnings).toEqual([
			{ path: 'where.children[0]', message: 'gone' },
			{ path: 'sort[0]', message: 'no sort' }
		]);
	});

	it('passes the capped total through', async () => {
		searchNodes.mockResolvedValue(page({ total: 1000, total_capped: true }));
		const result = await loadSmartCollection(collection(), {});
		expect(result.total).toBe(1000);
		expect(result.totalCapped).toBe(true);
	});

	it('returns a null query and does not search for a definition it cannot read', async () => {
		const result = await loadSmartCollection(
			collection({ definition: { v: 9 }, warnings: [{ path: 'where', message: 'm' }] }),
			{}
		);
		expect(searchNodes).not.toHaveBeenCalled();
		expect(result).toEqual({
			query: null,
			items: [],
			total: 0,
			totalCapped: false,
			nextCursor: null,
			warnings: [{ path: 'where', message: 'm' }]
		});
	});

	it('lets a search failure reject as a SearchError', async () => {
		searchNodes.mockResolvedValue({ error: { detail: 'x' }, response: { status: 500 } });
		await expect(loadSmartCollection(collection(), {})).rejects.toMatchObject({
			name: 'SearchError'
		});
	});
});

describe('manualCollections', () => {
	it('drops smart collections and keeps the order of the rest', () => {
		const list = [
			collection({ id: 'a', kind: 'manual', definition: null }),
			collection({ id: 'b' }),
			collection({ id: 'c', kind: 'manual', definition: null })
		];
		expect(manualCollections(list).map((c: { id: string }) => c.id)).toEqual(['a', 'c']);
	});
});

describe('describeCollectionCount', () => {
	it('keeps the manual wording', () => {
		const manual = (n: number) => collection({ kind: 'manual', item_count: n });
		expect(describeCollectionCount(manual(0))).toBe('No items');
		expect(describeCollectionCount(manual(1))).toBe('1 item');
		expect(describeCollectionCount(manual(12))).toBe('12 items');
	});

	it('uses the capped label for a smart collection', () => {
		expect(describeCollectionCount(collection({ item_count: 12 }))).toBe('12 items');
		expect(describeCollectionCount(collection({ item_count: 1 }))).toBe('1 item');
		expect(describeCollectionCount(collection({ item_count: 0 }))).toBe('No items');
		expect(describeCollectionCount(collection({ item_count: 1000, item_count_capped: true }))).toBe(
			'1,000+ items'
		);
	});
});

describe('describeSaveError', () => {
	it('numbers the condition the server rejected', () => {
		const two: Query = {
			v: 1,
			where: {
				op: 'and',
				children: [
					{ kind: 'favourite', value: true },
					{ kind: 'text', op: 'contains', value: 'x' } as never
				]
			},
			sort: []
		};
		const error = new SmartCollectionError(400, 'Bad value', 'where.children[1]', {
			where: [1]
		});
		expect(describeSaveError(error, two)).toBe('Condition 2: Bad value');
	});

	it('uses the message alone without a path', () => {
		expect(describeSaveError(new SmartCollectionError(409, 'Taken'), query)).toBe('Taken');
	});
});
