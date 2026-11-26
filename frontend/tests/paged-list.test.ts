import { describe, expect, it, vi } from 'vitest';
import { PagedList, type PageRequest } from '../src/lib/paged-list.svelte';

interface Row {
	id: string;
}

const rows = (from: number, count: number): Row[] =>
	Array.from({ length: count }, (_, i) => ({ id: `r${from + i}` }));

/** A page the way the generated client returns one: rows, and the headers the server sends. */
const page = (data: Row[], { next, total }: { next?: string; total?: number } = {}) => ({
	data,
	response: new Response(null, {
		headers: {
			...(next ? { link: `</api/v1/x?limit=2&after=${next}>; rel="next"` } : {}),
			...(total === undefined ? {} : { 'total-count': String(total) })
		}
	})
});

const failure = () => ({ error: { status: 503 }, response: new Response(null, { status: 503 }) });

type Fetch = (request: PageRequest<{ q: string }>) => Promise<ReturnType<typeof page>>;

/** A route that holds `count` rows and pages them `size` at a time, with opaque cursors. */
function route(count: number, size: number) {
	const calls: PageRequest<{ q: string }>[] = [];
	const fetchPage: Fetch = async (request) => {
		calls.push(request);
		const from = request.after === undefined ? 0 : Number(request.after.slice(1));
		const data = rows(from, Math.min(size, count - from));
		const more = from + size < count;
		return page(data, { next: more ? `c${from + size}` : undefined, total: count });
	};
	return { calls, fetchPage };
}

describe('PagedList, appending', () => {
	it('starts loading, with nothing', () => {
		const list = new PagedList<Row, { q: string }>(route(3, 2).fetchPage);
		expect(list.loading).toBe(true);
		expect(list.rows).toEqual([]);
		expect(list.hasMore).toBe(false);
	});

	it('reads the first page, and whether there is more and how many rows in all', async () => {
		const { fetchPage, calls } = route(5, 2);
		const list = new PagedList<Row, { q: string }>(fetchPage);

		await list.load({ q: 'jazz' });

		expect(list.rows.map((r) => r.id)).toEqual(['r0', 'r1']);
		expect(list.hasMore).toBe(true);
		expect(list.total).toBe(5);
		expect(list.loading).toBe(false);
		expect(calls).toEqual([{ after: undefined, params: { q: 'jazz' } }]);
	});

	it("asks for the next page with the server's cursor, not the last row's id", async () => {
		const { fetchPage, calls } = route(5, 2);
		const list = new PagedList<Row, { q: string }>(fetchPage);
		await list.load({ q: '' });

		await list.loadMore();
		await list.loadMore();

		expect(calls.map((c) => c.after)).toEqual([undefined, 'c2', 'c4']);
		expect(list.rows.map((r) => r.id)).toEqual(['r0', 'r1', 'r2', 'r3', 'r4']);
		expect(list.hasMore).toBe(false);
	});

	it('does nothing when there is no more, or a page is already loading', async () => {
		const { fetchPage, calls } = route(2, 2);
		const list = new PagedList<Row, { q: string }>(fetchPage);
		await list.load({ q: '' });

		await list.loadMore();

		expect(calls).toHaveLength(1);

		const busy = route(5, 2);
		const loading = new PagedList<Row, { q: string }>(busy.fetchPage);
		await loading.load({ q: '' });
		const first = loading.loadMore();
		await loading.loadMore();
		await first;
		expect(busy.calls).toHaveLength(2);
	});

	it('starts again from the first page when it is loaded for new params', async () => {
		const { fetchPage, calls } = route(5, 2);
		const list = new PagedList<Row, { q: string }>(fetchPage);
		await list.load({ q: '' });
		await list.loadMore();

		const again = list.load({ q: 'blues' });
		expect(list.rows).toEqual([]);
		expect(list.hasMore).toBe(false);
		await again;

		expect(list.rows.map((r) => r.id)).toEqual(['r0', 'r1']);
		expect(calls.at(-1)).toEqual({ after: undefined, params: { q: 'blues' } });
	});

	it('drops a page that arrives after a newer load', async () => {
		const resolvers: ((value: ReturnType<typeof page>) => void)[] = [];
		const fetchPage = vi.fn(
			() => new Promise<ReturnType<typeof page>>((resolve) => resolvers.push(resolve))
		);
		const list = new PagedList<Row, { q: string }>(fetchPage);

		const slow = list.load({ q: 'old' });
		const fast = list.load({ q: 'new' });
		resolvers[1](page(rows(10, 1)));
		await fast;
		resolvers[0](page(rows(0, 3)));
		await slow;

		expect(list.rows.map((r) => r.id)).toEqual(['r10']);
		expect(list.loading).toBe(false);
	});

	it('says the whole list failed when the first page does, and retries it', async () => {
		const ok = route(3, 2).fetchPage;
		const fetchPage = vi
			.fn<Fetch>()
			.mockResolvedValueOnce(failure() as never)
			.mockImplementation(ok);
		const list = new PagedList<Row, { q: string }>(fetchPage);

		await list.load({ q: '' });
		expect(list.failed).toBe(true);
		expect(list.hasMore).toBe(false);
		expect(list.loading).toBe(false);

		await list.retry();

		expect(list.failed).toBe(false);
		expect(list.rows).toHaveLength(2);
	});

	it('keeps the rows and the place when a later page fails, and resumes there', async () => {
		const ok = route(5, 2);
		const fetchPage = vi
			.fn<Fetch>()
			.mockImplementationOnce(ok.fetchPage)
			.mockResolvedValueOnce(failure() as never)
			.mockImplementation(ok.fetchPage);
		const list = new PagedList<Row, { q: string }>(fetchPage);
		await list.load({ q: '' });

		await list.loadMore();
		expect(list.nextFailed).toBe(true);
		expect(list.failed).toBe(false);
		expect(list.hasMore).toBe(true);
		expect(list.rows).toHaveLength(2);

		await list.retry();

		expect(list.nextFailed).toBe(false);
		expect(list.rows.map((r) => r.id)).toEqual(['r0', 'r1', 'r2', 'r3']);
		expect(ok.calls.map((c) => c.after)).toEqual([undefined, 'c2']);
	});

	it('does nothing to retry when nothing failed, or before it is loaded', async () => {
		const { fetchPage, calls } = route(3, 2);
		const list = new PagedList<Row, { q: string }>(fetchPage);
		await list.retry();
		await list.load({ q: '' });
		await list.retry();
		expect(calls).toHaveLength(1);
	});

	it('has no total when the server sends none, or sends nonsense', async () => {
		const data = rows(0, 1);
		const list = new PagedList<Row, { q: string }>(async () => page(data));
		await list.load({ q: '' });
		expect(list.total).toBeNull();

		const odd = new PagedList<Row, { q: string }>(async () => ({
			data,
			response: new Response(null, { headers: { 'total-count': 'many' } })
		}));
		await odd.load({ q: '' });
		expect(odd.total).toBeNull();
	});

	it('ignores the page-mode calls', async () => {
		const { fetchPage, calls } = route(5, 2);
		const list = new PagedList<Row, { q: string }>(fetchPage);
		await list.load({ q: '' });

		await list.next();
		await list.previous();
		await list.refresh();

		expect(calls).toHaveLength(1);
	});
});

describe('PagedList, in pages', () => {
	const paged = (count: number, size: number) => {
		const served = route(count, size);
		return {
			...served,
			list: new PagedList<Row, { q: string }>(served.fetchPage, { mode: 'page' })
		};
	};

	it('shows one page at a time, with its place in the whole list', async () => {
		const { list } = paged(5, 2);

		await list.load({ q: '' });
		expect([list.from, list.to, list.total]).toEqual([1, 2, 5]);

		await list.next();
		expect(list.rows.map((r) => r.id)).toEqual(['r2', 'r3']);
		expect([list.pageIndex, list.from, list.to]).toEqual([1, 3, 4]);

		await list.next();
		expect(list.rows.map((r) => r.id)).toEqual(['r4']);
		expect([list.from, list.to, list.hasMore]).toEqual([5, 5, false]);
	});

	it('goes back to a page it read before, with the cursor that read it', async () => {
		const { list, calls } = paged(5, 2);
		await list.load({ q: '' });
		await list.next();
		await list.next();

		await list.previous();
		expect(list.rows.map((r) => r.id)).toEqual(['r2', 'r3']);
		await list.previous();
		expect(list.rows.map((r) => r.id)).toEqual(['r0', 'r1']);
		expect(list.pageIndex).toBe(0);
		expect(list.hasMore).toBe(true);

		expect(calls.map((c) => c.after)).toEqual([undefined, 'c2', 'c4', 'c2', undefined]);
	});

	it('cannot go before the first page or past the last', async () => {
		const { list, calls } = paged(2, 2);
		await list.load({ q: '' });

		await list.previous();
		await list.next();

		expect(calls).toHaveLength(1);
		expect(list.pageIndex).toBe(0);
	});

	it('starts at the first page again for new params', async () => {
		const { list } = paged(5, 2);
		await list.load({ q: '' });
		await list.next();

		await list.load({ q: 'x' });

		expect([list.pageIndex, list.from]).toEqual([0, 1]);
	});

	it('keeps the page shown, and says so, when the next one would not load', async () => {
		const ok = route(5, 2);
		const fetchPage = vi
			.fn<Fetch>()
			.mockImplementationOnce(ok.fetchPage)
			.mockResolvedValueOnce(failure() as never)
			.mockImplementation(ok.fetchPage);
		const list = new PagedList<Row, { q: string }>(fetchPage, { mode: 'page' });
		await list.load({ q: '' });

		await list.next();
		expect(list.nextFailed).toBe(true);
		expect(list.failed).toBe(false);
		expect(list.rows.map((r) => r.id)).toEqual(['r0', 'r1']);
		expect(list.pageIndex).toBe(0);

		await list.retry();

		expect(list.nextFailed).toBe(false);
		expect(list.rows.map((r) => r.id)).toEqual(['r2', 'r3']);
		expect(list.pageIndex).toBe(1);
	});

	it('says the whole list failed when its first page does', async () => {
		const list = new PagedList<Row, { q: string }>(async () => failure() as never, {
			mode: 'page'
		});

		await list.load({ q: '' });

		expect(list.failed).toBe(true);
		expect([list.from, list.to]).toEqual([null, null]);
	});

	it('reads the page shown again after a change, keeping its rows meanwhile', async () => {
		let count = 5;
		const fetchPage: Fetch = async ({ after }) => {
			const from = after === undefined ? 0 : Number(after.slice(1));
			const data = rows(from, Math.max(0, Math.min(2, count - from)));
			return page(data, { next: from + 2 < count ? `c${from + 2}` : undefined, total: count });
		};
		const list = new PagedList<Row, { q: string }>(fetchPage, { mode: 'page' });
		await list.load({ q: '' });
		await list.next();

		count = 4;
		const again = list.refresh();
		expect(list.rows.map((r) => r.id)).toEqual(['r2', 'r3']);
		await again;

		expect(list.total).toBe(4);
		expect(list.hasMore).toBe(false);
	});

	it('shows the page before when the page it was on has emptied', async () => {
		let count = 5;
		const fetchPage: Fetch = async ({ after }) => {
			const from = after === undefined ? 0 : Number(after.slice(1));
			const data = rows(from, Math.max(0, Math.min(2, count - from)));
			return page(data, { next: from + 2 < count ? `c${from + 2}` : undefined, total: count });
		};
		const list = new PagedList<Row, { q: string }>(fetchPage, { mode: 'page' });
		await list.load({ q: '' });
		await list.next();
		await list.next();
		expect(list.rows.map((r) => r.id)).toEqual(['r4']);

		count = 4;
		await list.refresh();

		expect(list.pageIndex).toBe(1);
		expect(list.rows.map((r) => r.id)).toEqual(['r2', 'r3']);
		expect([list.from, list.to]).toEqual([3, 4]);
	});

	it('drops a page that arrives after a newer request', async () => {
		const resolvers: ((value: ReturnType<typeof page>) => void)[] = [];
		const fetchPage = vi.fn(
			() => new Promise<ReturnType<typeof page>>((resolve) => resolvers.push(resolve))
		);
		const list = new PagedList<Row, { q: string }>(fetchPage, { mode: 'page' });

		const slow = list.load({ q: 'old' });
		const fast = list.load({ q: 'new' });
		resolvers[1](page(rows(10, 1)));
		await fast;
		resolvers[0](page(rows(0, 3)));
		await slow;

		expect(list.rows.map((r) => r.id)).toEqual(['r10']);
	});
});

describe('PagedList, when a read goes wrong', () => {
	it('keeps what failed, so the page can word the error, and clears it on success', async () => {
		const bad = failure();
		const ok = route(3, 2).fetchPage;
		const fetchPage = vi
			.fn<Fetch>()
			.mockResolvedValueOnce(bad as never)
			.mockImplementation(ok);
		const list = new PagedList<Row, { q: string }>(fetchPage);

		await list.load({ q: '' });
		expect(list.failure).toBe(bad);

		await list.retry();
		expect(list.failure).toBeNull();
	});

	it('treats a request that throws as a failed page', async () => {
		const list = new PagedList<Row, { q: string }>(async () => {
			throw new TypeError('network down');
		});

		await list.load({ q: '' });

		expect(list.failed).toBe(true);
		expect(list.loading).toBe(false);
		expect(list.failure?.error).toBeInstanceOf(TypeError);
	});
});
