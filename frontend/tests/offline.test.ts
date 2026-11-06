import { beforeEach, describe, expect, it } from 'vitest';
import { offlineController } from '../src/lib/offline.svelte';
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
