import { beforeEach, describe, expect, it, vi } from 'vitest';

const { countNodes } = vi.hoisted(() => ({ countNodes: vi.fn() }));
vi.mock('$lib/api/client', () => ({ countNodes, listNodes: vi.fn(), searchNodes: vi.fn() }));

import { formatTotal, readListCount } from '$lib/query/items-page';
import { createCountTracker, fetchExactCount } from '$lib/query/search-count';

beforeEach(() => vi.resetAllMocks());

describe('readListCount', () => {
	it('reads the total and the capped flag', () => {
		const headers = new Headers({ 'Total-Count': '1000', 'Total-Count-Capped': 'true' });
		expect(readListCount(headers)).toEqual({ total: 1000, capped: true });
		expect(formatTotal(1000, true)).toBe('1,000+ items');
	});

	it('is exact without the flag', () => {
		expect(readListCount(new Headers({ 'Total-Count': '7' }))).toEqual({
			total: 7,
			capped: false
		});
	});

	it('ignores a missing or malformed count', () => {
		expect(readListCount(new Headers())).toEqual({ total: null, capped: false });
		expect(readListCount(undefined)).toEqual({ total: null, capped: false });
		expect(
			readListCount(new Headers({ 'Total-Count': 'x', 'Total-Count-Capped': 'true' }))
		).toEqual({ total: null, capped: false });
	});
});

describe('fetchExactCount', () => {
	it('sends the same filters and returns the count', async () => {
		countNodes.mockResolvedValue({ data: { count: 1005 } });
		expect(await fetchExactCount({ q: 'foo', type: 'game' })).toBe(1005);
		expect(countNodes).toHaveBeenCalledWith({ query: { q: 'foo', type: 'game' } });
	});

	it('is null on an error response or a thrown error', async () => {
		countNodes.mockResolvedValueOnce({ error: {} });
		expect(await fetchExactCount({ q: 'foo', type: null })).toBeNull();
		countNodes.mockRejectedValueOnce(new Error('offline'));
		expect(await fetchExactCount({ q: 'foo', type: null })).toBeNull();
	});
});

describe('createCountTracker', () => {
	const defer = () => {
		let resolve!: (n: number | null) => void;
		const promise = new Promise<number | null>((r) => (resolve = r));
		return { promise, resolve };
	};

	it('applies the exact count', async () => {
		const apply = vi.fn();
		await createCountTracker(async () => 1005).run({ q: 'a', type: null }, apply);
		expect(apply).toHaveBeenCalledWith(1005);
	});

	it('drops a late count after newer filters', async () => {
		const first = defer();
		const second = defer();
		const fetchCount = vi
			.fn()
			.mockReturnValueOnce(first.promise)
			.mockReturnValueOnce(second.promise);
		const tracker = createCountTracker(fetchCount);
		const apply = vi.fn();
		const a = tracker.run({ q: 'a', type: null }, apply);
		const b = tracker.run({ q: 'ab', type: null }, apply);
		second.resolve(2);
		first.resolve(1);
		await Promise.all([a, b]);
		expect(apply).toHaveBeenCalledTimes(1);
		expect(apply).toHaveBeenCalledWith(2);
	});

	it('drops a count after cancel', async () => {
		const pending = defer();
		const tracker = createCountTracker(() => pending.promise);
		const apply = vi.fn();
		const run = tracker.run({ q: 'a', type: null }, apply);
		tracker.cancel();
		pending.resolve(5);
		await run;
		expect(apply).not.toHaveBeenCalled();
	});

	it('keeps the capped figure when the count fails', async () => {
		const apply = vi.fn();
		await createCountTracker(async () => null).run({ q: 'a', type: null }, apply);
		expect(apply).not.toHaveBeenCalled();
	});
});
