import { beforeEach, describe, expect, it, vi } from 'vitest';

const { searchNodes } = vi.hoisted(() => ({ searchNodes: vi.fn() }));
vi.mock('$lib/api/client', () => ({ searchNodes }));
import { runSearch, SearchError } from '$lib/query/search';
import type { Query } from '$lib/query/types';

const query: Query = {
	v: 1,
	where: { op: 'and', children: [{ kind: 'favourite', value: true }] },
	sort: []
};
const respond = (status: number) => ({ status }) as Response;

beforeEach(() => vi.resetAllMocks());

async function failure(promise: Promise<unknown>): Promise<SearchError> {
	try {
		await promise;
	} catch (e) {
		expect(e).toBeInstanceOf(SearchError);
		return e as SearchError;
	}
	throw new Error('expected runSearch to reject');
}

describe('runSearch', () => {
	it('maps the response', async () => {
		searchNodes.mockResolvedValue({
			data: {
				items: [{ id: 'a' }],
				total: 1000,
				total_capped: true,
				next_cursor: 'abc',
				warnings: [{ path: 'where.children[0]', message: 'gone' }]
			},
			response: respond(200)
		});
		expect(await runSearch({ query })).toEqual({
			items: [{ id: 'a' }],
			total: 1000,
			totalCapped: true,
			nextCursor: 'abc',
			warnings: [{ path: 'where.children[0]', message: 'gone' }]
		});
	});

	it('maps a missing cursor to null', async () => {
		searchNodes.mockResolvedValue({
			data: { items: [], total: 0, total_capped: false, warnings: [] },
			response: respond(200)
		});
		expect((await runSearch({ query })).nextCursor).toBeNull();
	});

	it('sends the query with the default limit and no cursor', async () => {
		searchNodes.mockResolvedValue({
			data: { items: [], total: 0, total_capped: false, warnings: [] },
			response: respond(200)
		});
		await runSearch({ query });
		expect(searchNodes).toHaveBeenCalledWith({ body: { query, limit: 50, cursor: null } });
	});

	it('sends a custom limit and cursor', async () => {
		searchNodes.mockResolvedValue({
			data: { items: [], total: 0, total_capped: false, warnings: [] },
			response: respond(200)
		});
		await runSearch({ query, limit: 10, cursor: 'next' });
		expect(searchNodes).toHaveBeenCalledWith({ body: { query, limit: 10, cursor: 'next' } });
	});

	it('carries the status and detail of a 400', async () => {
		searchNodes.mockResolvedValue({
			error: { detail: 'where.children[0].op: unknown operator' },
			response: respond(400)
		});
		const error = await failure(runSearch({ query }));
		expect(error.status).toBe(400);
		expect(error.detail).toBe('where.children[0].op: unknown operator');
	});

	it('joins the messages of a 422', async () => {
		searchNodes.mockResolvedValue({
			error: { detail: [{ msg: 'too long' }, { msg: 'bad' }] },
			response: respond(422)
		});
		const error = await failure(runSearch({ query }));
		expect(error.status).toBe(422);
		expect(error.detail).toBe('too long, bad');
	});

	it('gives a server error a generic message and no detail', async () => {
		searchNodes.mockResolvedValue({ error: { detail: 'boom' }, response: respond(500) });
		const error = await failure(runSearch({ query }));
		expect(error.status).toBe(500);
		expect(error.detail).toBeNull();
		expect(error.title).toBe('Something went wrong');
	});

	it('reports a missing response as offline', async () => {
		searchNodes.mockResolvedValue({ error: undefined, response: undefined });
		const error = await failure(runSearch({ query }));
		expect(error.status).toBeNull();
		expect(error.detail).toBeNull();
		expect(error.title).toBe('You appear to be offline');
	});

	it('reports a rejected request as offline', async () => {
		searchNodes.mockRejectedValue(new TypeError('Failed to fetch'));
		const error = await failure(runSearch({ query }));
		expect(error.status).toBeNull();
		expect(error.title).toBe('You appear to be offline');
	});
});
