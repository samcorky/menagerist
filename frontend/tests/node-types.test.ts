import { beforeEach, describe, expect, it, vi } from 'vitest';

const { listNodeTypes } = vi.hoisted(() => ({ listNodeTypes: vi.fn() }));
vi.mock('$lib/api/client', () => ({ listNodeTypes }));

import { effectiveSchema, fetchAllNodeTypes, NODE_TYPES_PAGE_SIZE } from '$lib/node-types';

const type = (n: number) => ({ id: `id-${n}`, slug: `type-${n}`, label: `Type ${n}` });
const page = (from: number, count: number, next: boolean) => ({
	data: Array.from({ length: count }, (_, i) => type(from + i)),
	response: new Response(null, {
		headers: next ? { link: '</api/v1/node-types?after=x>; rel="next"' } : {}
	})
});

beforeEach(() => vi.resetAllMocks());

describe('fetchAllNodeTypes', () => {
	it('follows the next link until every type is read', async () => {
		const size = NODE_TYPES_PAGE_SIZE;
		listNodeTypes
			.mockResolvedValueOnce(page(0, size, true))
			.mockResolvedValueOnce(page(size, size, true))
			.mockResolvedValueOnce(page(2 * size, 3, false));

		const all = await fetchAllNodeTypes();

		expect(all?.map((t) => t.slug)).toEqual(
			Array.from({ length: 2 * size + 3 }, (_, i) => `type-${i}`)
		);
		expect(listNodeTypes.mock.calls.map(([options]) => options.query)).toEqual([
			{ after: undefined, limit: size },
			{ after: `id-${size - 1}`, limit: size },
			{ after: `id-${2 * size - 1}`, limit: size }
		]);
	});

	it('makes one request when there is no next link', async () => {
		listNodeTypes.mockResolvedValueOnce(page(0, 2, false));
		expect(await fetchAllNodeTypes()).toHaveLength(2);
		expect(listNodeTypes).toHaveBeenCalledTimes(1);
	});

	it('returns null when any page fails, never a partial list', async () => {
		listNodeTypes
			.mockResolvedValueOnce(page(0, NODE_TYPES_PAGE_SIZE, true))
			.mockResolvedValueOnce({ error: { detail: 'boom' }, response: new Response(null) });
		expect(await fetchAllNodeTypes()).toBeNull();
	});
});

describe('effectiveSchema', () => {
	const own = { type: 'object', properties: { width: { type: 'string' } } };
	const joined = {
		type: 'object',
		properties: { condition: { type: 'string' }, width: { type: 'string' } }
	};

	it('is the fields a subtype uses, its parent`s and its own, when the server gives them', () => {
		expect(effectiveSchema({ attributes_schema: own, effective_schema: joined })).toEqual(joined);
	});

	it('falls back to the type`s own fields when there is no effective schema', () => {
		expect(effectiveSchema({ attributes_schema: own })).toEqual(own);
		expect(effectiveSchema({ attributes_schema: own, effective_schema: null })).toEqual(own);
	});

	it('is null for a type with no fields, an unknown type or none at all', () => {
		expect(effectiveSchema({ attributes_schema: null, effective_schema: null })).toBeNull();
		expect(effectiveSchema(undefined)).toBeNull();
		expect(effectiveSchema(null)).toBeNull();
	});
});
