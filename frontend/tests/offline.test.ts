import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
	OfflineController,
	PROBE_DELAYS_MS,
	offlineController,
	unreachableWording
} from '../src/lib/offline.svelte';
import { OFFLINE_MESSAGE } from '../src/lib/offline';
import { networkAwareError, uploadErrorMessage } from '../src/lib/api/errors';

describe('the offline wording', () => {
	it('is one sentence shared by every screen', () => {
		expect(OFFLINE_MESSAGE).toBe('You appear to be offline. Check your connection and try again.');
		expect(uploadErrorMessage({ response: undefined })).toBe(OFFLINE_MESSAGE);
		expect(networkAwareError({ response: undefined }).title).toBe('You appear to be offline');
	});

	it('is not used when the server answered', () => {
		const response = new Response(null, { status: 500 });
		expect(networkAwareError({ response }).title).toBe('Something went wrong');
	});
});

describe('offlineController', () => {
	beforeEach(() => {
		offlineController.reportReachable();
	});

	it('is offline from a failed request until the server answers', () => {
		expect(offlineController.offline).toBe(false);
		offlineController.reportUnreachable();
		expect(offlineController.offline).toBe(true);
		offlineController.reportReachable();
		expect(offlineController.offline).toBe(false);
	});

	it('asks pages to load again when the server comes back, not on every answer', () => {
		const before = offlineController.retryCount;
		offlineController.reportReachable();
		expect(offlineController.retryCount).toBe(before);
		offlineController.reportUnreachable();
		offlineController.reportReachable();
		expect(offlineController.retryCount).toBe(before + 1);
	});

	it('retries on demand', () => {
		const before = offlineController.retryCount;
		offlineController.retry();
		expect(offlineController.retryCount).toBe(before + 1);
	});
});

describe('offlineController probing', () => {
	afterEach(() => {
		vi.useRealTimers();
	});

	it('checks back by itself while the server cannot be reached, then reloads pages', async () => {
		vi.useFakeTimers();
		let up = false;
		const probes: number[] = [];
		const controller = new OfflineController(async () => {
			probes.push(Date.now());
			return up;
		});
		const before = controller.retryCount;

		controller.reportUnreachable();
		await vi.advanceTimersByTimeAsync(PROBE_DELAYS_MS[0]);
		expect(probes).toHaveLength(1);
		expect(controller.offline).toBe(true);

		up = true;
		await vi.advanceTimersByTimeAsync(PROBE_DELAYS_MS[1]);
		expect(controller.offline).toBe(false);
		expect(controller.retryCount).toBe(before + 1);

		// Once the server is back nothing keeps probing.
		await vi.advanceTimersByTimeAsync(120_000);
		expect(probes).toHaveLength(2);
	});

	it('backs off, and stops as soon as any request gets an answer', async () => {
		vi.useFakeTimers();
		let calls = 0;
		const controller = new OfflineController(async () => {
			calls += 1;
			return false;
		});
		controller.reportUnreachable();
		controller.reportUnreachable();
		const total = PROBE_DELAYS_MS.reduce((sum, delay) => sum + delay, 0);
		await vi.advanceTimersByTimeAsync(total);
		expect(calls).toBe(PROBE_DELAYS_MS.length);
		await vi.advanceTimersByTimeAsync(PROBE_DELAYS_MS.at(-1)!);
		expect(calls).toBe(PROBE_DELAYS_MS.length + 1);

		controller.reportReachable();
		await vi.advanceTimersByTimeAsync(120_000);
		expect(calls).toBe(PROBE_DELAYS_MS.length + 1);
	});

	it('treats a failing probe as still unreachable', async () => {
		vi.useFakeTimers();
		const controller = new OfflineController(async () => {
			throw new TypeError('no route');
		});
		controller.reportUnreachable();
		await vi.advanceTimersByTimeAsync(PROBE_DELAYS_MS[0]);
		expect(controller.offline).toBe(true);
		controller.reportReachable();
	});
});

describe('why the server cannot be reached', () => {
	it('tells a lost connection from a server that is away', () => {
		const controller = new OfflineController(async () => false);
		controller.reportUnreachable();
		expect(controller.offline).toBe(true);
		// The browser still has a network: the server (or the proxy in front of it) is the problem.
		expect(controller.browserOffline).toBe(false);
		controller.reportReachable();
	});

	it('words each case for the screens that show it', () => {
		expect(unreachableWording(true)).toEqual({
			title: "You're offline",
			detail: 'Check your connection, then try again.',
			cantLoad: "You're offline, so"
		});
		expect(unreachableWording(false)).toEqual({
			title: "Can't reach Menagerist",
			detail: "The server isn't answering. This page will load by itself when it's back.",
			cantLoad: "Can't reach Menagerist, so"
		});
	});
});
