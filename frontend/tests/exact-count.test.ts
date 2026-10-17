import { beforeEach, describe, expect, it, vi } from 'vitest';

const { fetchExactCount } = vi.hoisted(() => ({ fetchExactCount: vi.fn() }));
vi.mock('$lib/smart-collections', () => ({ fetchExactCount }));

import { ExactCount } from '$lib/exact-count.svelte';

function deferred<T>() {
	let resolve!: (value: T) => void;
	let reject!: (reason: unknown) => void;
	const promise = new Promise<T>((res, rej) => {
		resolve = res;
		reject = rej;
	});
	return { promise, resolve, reject };
}

describe('ExactCount', () => {
	beforeEach(() => {
		fetchExactCount.mockReset();
	});

	it('fires once per scope and stores the figure', async () => {
		fetchExactCount.mockResolvedValue(1284);
		const exact = new ExactCount();
		exact.track('c1:a');
		exact.auto('c1');
		await vi.waitFor(() => expect(exact.count).toBe(1284));
		exact.track('c1:a');
		exact.auto('c1');
		expect(fetchExactCount).toHaveBeenCalledTimes(1);
		expect(fetchExactCount.mock.calls[0][1]).toBeInstanceOf(AbortSignal);
	});

	it('discards the figure and fires again when the scope changes', async () => {
		fetchExactCount.mockResolvedValue(5);
		const exact = new ExactCount();
		exact.track('c1:a');
		exact.auto('c1');
		await vi.waitFor(() => expect(exact.count).toBe(5));
		exact.track('c1:b');
		expect(exact.count).toBeNull();
		exact.auto('c1');
		expect(fetchExactCount).toHaveBeenCalledTimes(2);
	});

	it('ignores a late reply for an old scope and aborts its request', async () => {
		const old = deferred<number>();
		fetchExactCount.mockReturnValueOnce(old.promise);
		const exact = new ExactCount();
		exact.track('c1:a');
		exact.auto('c1');
		const signal: AbortSignal = fetchExactCount.mock.calls[0][1];
		exact.track('c2:a');
		expect(signal.aborted).toBe(true);
		old.resolve(999);
		await old.promise;
		expect(exact.count).toBeNull();
		expect(exact.loading).toBe(false);
	});

	it('flags a failure, then recovers on retry', async () => {
		fetchExactCount.mockRejectedValueOnce(new Error('boom')).mockResolvedValueOnce(1284);
		const exact = new ExactCount();
		exact.track('c1:a');
		exact.auto('c1');
		await vi.waitFor(() => expect(exact.failed).toBe(true));
		expect(exact.loading).toBe(false);
		exact.auto('c1');
		expect(fetchExactCount).toHaveBeenCalledTimes(1);
		void exact.retry('c1');
		expect(exact.failed).toBe(false);
		expect(exact.loading).toBe(true);
		await vi.waitFor(() => expect(exact.count).toBe(1284));
		expect(exact.failed).toBe(false);
	});

	it('does nothing until asked, so an uncapped collection never fires', () => {
		const exact = new ExactCount();
		exact.track('c1:a');
		expect(fetchExactCount).not.toHaveBeenCalled();
	});
});
