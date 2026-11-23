import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { deleteNodes, toastSuccess } = vi.hoisted(() => ({
	deleteNodes: vi.fn(),
	toastSuccess: vi.fn()
}));
vi.mock('$lib/api/client', () => ({ deleteNodes }));
vi.mock('svelte-sonner', () => ({ toast: { success: toastSuccess, error: vi.fn() } }));

import { PendingDeletes } from '../src/lib/pending-deletes.svelte';

const hooks = () => ({ onsent: vi.fn().mockResolvedValue(undefined), onmissing: vi.fn() });

beforeEach(() => {
	vi.useFakeTimers();
	deleteNodes.mockReset().mockResolvedValue({ data: undefined, error: undefined });
	toastSuccess.mockReset();
});
afterEach(() => vi.useRealTimers());

describe('PendingDeletes', () => {
	it('hides the items at once and sends nothing until the window ends', async () => {
		const pending = new PendingDeletes();
		pending.start(['a', 'b'], hooks());
		expect(pending.hidden.has('a')).toBe(true);
		expect(deleteNodes).not.toHaveBeenCalled();
		expect(toastSuccess).toHaveBeenCalledWith('2 items deleted', expect.anything());

		await vi.advanceTimersByTimeAsync(5000);
		expect(deleteNodes).toHaveBeenCalledWith({ body: { ids: ['a', 'b'] } });
	});

	it('Undo sends nothing and shows the items again', async () => {
		const pending = new PendingDeletes();
		pending.start(['a'], hooks());
		toastSuccess.mock.calls[0][1].action.onClick();
		await vi.advanceTimersByTimeAsync(10_000);
		expect(deleteNodes).not.toHaveBeenCalled();
		expect(pending.hidden.has('a')).toBe(false);
	});

	it('leaving the page sends a pending delete once', async () => {
		const pending = new PendingDeletes();
		const h = hooks();
		pending.start(['a'], h);
		await pending.flushAll();
		await vi.advanceTimersByTimeAsync(10_000);
		expect(deleteNodes).toHaveBeenCalledTimes(1);
		expect(h.onsent).toHaveBeenCalledTimes(1);
		expect(pending.hidden.has('a')).toBe(false);
	});

	it('shows the items again and reports the missing ones when the server refuses', async () => {
		const gone = '01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e10';
		deleteNodes.mockResolvedValue({
			error: { detail: `Unknown or deleted items: ${gone}` },
			response: { status: 400 }
		});
		const pending = new PendingDeletes();
		const h = hooks();
		pending.start(['a', gone], h);
		await pending.flushAll();
		expect(h.onmissing).toHaveBeenCalledWith([gone]);
		expect(h.onsent).not.toHaveBeenCalled();
		expect(pending.hidden.size).toBe(0);
	});
});
