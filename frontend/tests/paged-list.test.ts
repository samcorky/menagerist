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

describe('PagedList, with a cursor and a total in the result', () => {
	it('takes the next cursor and the count from the result, not from headers', async () => {
		const calls: (string | undefined)[] = [];
		const list = new PagedList<Row, null>(async ({ after }) => {
			calls.push(after);
			const second = after === 'c2';
			return {
				data: second ? rows(2, 1) : rows(0, 2),
				cursor: second ? null : 'c2',
				total: 3
			};
		});

		await list.load(null);
		expect([list.hasMore, list.total, list.rows.length]).toEqual([true, 3, 2]);

		await list.loadMore();
		expect(calls).toEqual([undefined, 'c2']);
		expect([list.hasMore, list.total, list.rows.length]).toEqual([false, 3, 3]);
	});

	it('lets the result say there is no count, whatever a header says', async () => {
		const list = new PagedList<Row, null>(async () => ({
			data: rows(0, 1),
			response: new Response(null, { headers: { 'total-count': '9' } }),
			total: null
		}));
		await list.load(null);
		expect(list.total).toBeNull();
	});

	it('says a further page is being read, and a new load is not one', async () => {
		let release: () => void = () => {};
		const list = new PagedList<Row, null>(async ({ after }) => {
			if (after !== undefined) await new Promise<void>((resolve) => (release = resolve));
			return {
				data: rows(after === undefined ? 0 : 2, 2),
				cursor: after === undefined ? 'c2' : null
			};
		});
		await list.load(null);
		expect(list.loadingMore).toBe(false);

		const more = list.loadMore();
		expect([list.loading, list.loadingMore]).toEqual([true, true]);
		release();
		await more;
		expect([list.loading, list.loadingMore]).toEqual([false, false]);

		const again = list.load(null, { keepRows: true });
		expect([list.loading, list.loadingMore]).toEqual([true, false]);
		await again;
	});
});

describe('PagedList.clear', () => {
	it('empties the list at once and drops a read that is still in flight', async () => {
		let release: () => void = () => {};
		const list = new PagedList<Row, null>(async ({ after }) => {
			if (after === undefined && list.rows.length > 0) {
				await new Promise<void>((resolve) => (release = resolve));
			}
			return { data: rows(0, 2), cursor: 'c2', total: 9 };
		});
		await list.load(null);
		expect([list.rows.length, list.hasMore, list.total]).toEqual([2, true, 9]);

		const slow = list.load(null, { keepRows: true });
		list.clear();
		expect([list.rows.length, list.hasMore, list.total, list.loading]).toEqual([
			0,
			false,
			null,
			false
		]);

		release();
		await slow;
		// The answer to the read it dropped does not come back.
		expect([list.rows.length, list.hasMore, list.total]).toEqual([0, false, null]);
	});

	it('forgets a failure, so a list that shows something else starts clean', async () => {
		const list = new PagedList<Row, null>(async () => failure());
		await list.load(null);
		expect(list.failed).toBe(true);

		list.clear();
		expect([list.failed, list.nextFailed, list.failure]).toEqual([false, false, null]);
		await list.retry();
		expect(list.failed).toBe(false);
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

	it('keeps the rows on screen while it starts again, when asked to', async () => {
		const { list, calls } = paged(5, 2);
		await list.load({ q: '' });
		await list.next();

		const again = list.load({ q: 'x' }, { keepRows: true });
		// Nothing has emptied or moved: the page is where it was until the new first page is in.
		expect(list.rows.map((r) => r.id)).toEqual(['r2', 'r3']);
		expect([list.pageIndex, list.from, list.to, list.loading]).toEqual([1, 3, 4, true]);
		await again;

		expect(list.rows.map((r) => r.id)).toEqual(['r0', 'r1']);
		expect([list.pageIndex, list.from, list.to, list.loading]).toEqual([0, 1, 2, false]);
		expect(calls.at(-1)).toEqual({ after: undefined, params: { q: 'x' } });
		// The pages after it are read afresh: Next uses the new first page's cursor.
		await list.next();
		expect(list.rows.map((r) => r.id)).toEqual(['r2', 'r3']);
		await list.previous();
		expect(list.rows.map((r) => r.id)).toEqual(['r0', 'r1']);
	});

	it('shows the rows that were kept, with a retry, when the new first page fails', async () => {
		let fail = false;
		const served = route(5, 2);
		const list = new PagedList<Row, { q: string }>(
			async (request) => (fail ? (failure() as never) : served.fetchPage(request)),
			{ mode: 'page' }
		);
		await list.load({ q: '' });

		fail = true;
		await list.load({ q: 'x' }, { keepRows: true });
		expect(list.rows.map((r) => r.id)).toEqual(['r0', 'r1']);
		expect([list.failed, list.nextFailed]).toEqual([false, true]);

		fail = false;
		await list.retry();
		expect(list.nextFailed).toBe(false);
		expect(list.rows.map((r) => r.id)).toEqual(['r0', 'r1']);
	});

	it('empties as usual when asked to keep rows but has none yet', async () => {
		const { list } = paged(3, 2);
		const first = list.load({ q: '' }, { keepRows: true });
		expect(list.rows).toEqual([]);
		await first;
		expect(list.rows).toHaveLength(2);
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

describe('PagedList.count', () => {
	it("is the server's count when it sends one", async () => {
		const list = new PagedList<Row, { q: string }>(route(5, 2).fetchPage, { mode: 'page' });
		await list.load({ q: '' });
		expect(list.count).toBe(5);
	});

	it('is the rows when they fit one page and the server sent no count', async () => {
		const list = new PagedList<Row, { q: string }>(async () => page(rows(0, 3)), { mode: 'page' });
		expect(list.count).toBeNull();
		await list.load({ q: '' });
		expect(list.count).toBe(3);
	});

	it('is unknown with more pages and no count from the server', async () => {
		const list = new PagedList<Row, { q: string }>(async () => page(rows(0, 2), { next: 'c2' }), {
			mode: 'page'
		});
		await list.load({ q: '' });
		expect(list.count).toBeNull();
	});
});
