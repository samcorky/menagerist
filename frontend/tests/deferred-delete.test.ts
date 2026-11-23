import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { deferDelete } from '../src/lib/deferred-delete';

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe('deferDelete', () => {
	it('sends once after the 5 second window', async () => {
		const send = vi.fn().mockResolvedValue(undefined);
		deferDelete(send);
		await vi.advanceTimersByTimeAsync(4999);
		expect(send).not.toHaveBeenCalled();
		await vi.advanceTimersByTimeAsync(1);
		expect(send).toHaveBeenCalledTimes(1);
	});

	it('sends nothing when undone inside the window', async () => {
		const send = vi.fn().mockResolvedValue(undefined);
		const pending = deferDelete(send);
		pending.undo();
		await vi.advanceTimersByTimeAsync(10_000);
		expect(send).not.toHaveBeenCalled();
		await expect(pending.settled).resolves.toBeUndefined();
	});

	it('flush sends at once and the timer then sends nothing more', async () => {
		const send = vi.fn().mockResolvedValue(undefined);
		const pending = deferDelete(send);
		await pending.flush();
		expect(send).toHaveBeenCalledTimes(1);
		await vi.advanceTimersByTimeAsync(10_000);
		expect(send).toHaveBeenCalledTimes(1);
	});

	it('undo after the send does nothing', async () => {
		const send = vi.fn().mockResolvedValue(undefined);
		const pending = deferDelete(send);
		await pending.flush();
		pending.undo();
		expect(send).toHaveBeenCalledTimes(1);
	});

	it('reports a failed send to the caller of flush', async () => {
		const pending = deferDelete(() => Promise.reject(new Error('offline')));
		await expect(pending.flush()).rejects.toThrow('offline');
	});

	it('honours a custom window', async () => {
		const send = vi.fn().mockResolvedValue(undefined);
		deferDelete(send, { windowMs: 100 });
		await vi.advanceTimersByTimeAsync(100);
		expect(send).toHaveBeenCalledTimes(1);
	});
});
