import { describe, expect, it, vi } from 'vitest';
import { nextCursor, readPages } from '../src/lib/paging';

const rows = (from: number, count: number) =>
	Array.from({ length: count }, (_, i) => ({ id: `n${from + i}` }));
const page = (data: unknown[], next?: string) => ({
	data,
	response: new Response(null, {
		headers: next ? { link: `</api/v1/x?limit=100&after=${next}>; rel="next"` } : {}
	})
});

describe('nextCursor', () => {
	it('reads the cursor the next link carries, decoded', () => {
		expect(nextCursor('</x?limit=2&after=eyJ2IjoxfQ>; rel="next"')).toBe('eyJ2IjoxfQ');
		expect(nextCursor('</x?after=a%20b>; rel="next"')).toBe('a b');
	});
	it('is null without a next link, a cursor or a readable one', () => {
		expect(nextCursor(null)).toBeNull();
		expect(nextCursor('</x?after=a>; rel="prev"')).toBeNull();
		expect(nextCursor('</x>; rel="next"')).toBeNull();
		expect(nextCursor('</x?after=%E0%A4%A>; rel="next"')).toBeNull();
	});
});

describe('readPages', () => {
	it('follows the next cursor a page at a time until there is none', async () => {
		const fetchPage = vi
			.fn()
			.mockResolvedValueOnce(page(rows(0, 100), 'c1'))
			.mockResolvedValueOnce(page(rows(100, 40)));
		const read = await readPages(fetchPage);
		expect(read.ok).toBe(true);
		expect(read.rows).toHaveLength(140);
		expect(fetchPage.mock.calls).toEqual([[undefined], ['c1']]);
	});

	it('stops at the most rows it was asked for', async () => {
		const fetchPage = vi.fn().mockResolvedValue(page(rows(0, 100), 'more'));
		const read = await readPages(fetchPage, { maxRows: 250 });
		expect(read.rows).toHaveLength(250);
		expect(fetchPage).toHaveBeenCalledTimes(3);
	});

	it('stops at the most pages it was asked for', async () => {
		const fetchPage = vi.fn().mockResolvedValue(page(rows(0, 10), 'more'));
		const read = await readPages(fetchPage, { maxPages: 2 });
		expect(read).toMatchObject({ ok: true });
		expect(read.rows).toHaveLength(20);
	});

	it('reports a failed page and keeps what was read before it', async () => {
		const fetchPage = vi
			.fn()
			.mockResolvedValueOnce(page(rows(0, 100), 'c1'))
			.mockResolvedValueOnce({ error: { detail: 'boom' }, response: new Response(null) });
		const read = await readPages(fetchPage);
		expect(read.ok).toBe(false);
		expect(read.rows).toHaveLength(100);
		expect('failure' in read && read.failure.error).toEqual({ detail: 'boom' });
	});
});
