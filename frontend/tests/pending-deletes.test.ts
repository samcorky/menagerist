import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { deleteNodes, toastSuccess, toastDismiss } = vi.hoisted(() => ({
	deleteNodes: vi.fn(),
	toastSuccess: vi.fn(),
	toastDismiss: vi.fn()
}));
vi.mock('$lib/api/client', () => ({ deleteNodes }));
vi.mock('svelte-sonner', () => ({
	toast: { success: toastSuccess, error: vi.fn(), dismiss: toastDismiss }
}));

import { PendingDeletes } from '../src/lib/pending-deletes.svelte';

const hooks = () => ({
	onsent: vi.fn().mockResolvedValue(undefined),
	onmissing: vi.fn(),
	onrestore: vi.fn()
});

beforeEach(() => {
	vi.useFakeTimers();
	deleteNodes.mockReset().mockResolvedValue({ data: undefined, error: undefined });
	toastSuccess.mockReset().mockReturnValue('toast-1');
	toastDismiss.mockReset();
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
		const h = hooks();
		pending.start(['a'], h);
		toastSuccess.mock.calls[0][1].action.onClick();
		await vi.advanceTimersByTimeAsync(10_000);
		expect(deleteNodes).not.toHaveBeenCalled();
		expect(pending.hidden.has('a')).toBe(false);
		expect(h.onrestore).toHaveBeenCalledTimes(1);
	});

	it('closes the Undo toast when leaving the page sends the delete', async () => {
		const pending = new PendingDeletes();
		pending.start(['a'], hooks());
		await pending.flushAll();
		expect(toastDismiss).toHaveBeenCalledWith('toast-1');
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
		expect(h.onrestore).toHaveBeenCalledTimes(1);
		expect(pending.hidden.size).toBe(0);
	});
});
