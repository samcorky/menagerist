import { describe, it, expect, vi, beforeEach } from 'vitest';
import '../src/lib/api/client'; // register interceptor side-effects
import { client } from '../src/lib/api/generated/client.gen';
import { versionController } from '../src/lib/version.svelte';

describe('version-header-interceptor', () => {
	beforeEach(() => {
		vi.restoreAllMocks();
		versionController.mismatch = null;
	});

	it('calls report() with the App-Version header value', async () => {
		const reportSpy = vi.spyOn(versionController, 'report');

		vi.stubGlobal(
			'fetch',
			async () =>
				new Response('{}', {
					status: 200,
					headers: { 'Content-Type': 'application/json', 'App-Version': '2.0.0' }
				})
		);

		await client.get({ url: '/api/anything' });

		expect(reportSpy).toHaveBeenCalledOnce();
		expect(reportSpy).toHaveBeenCalledWith('2.0.0');
	});

	it('does not call report() when App-Version header is absent', async () => {
		const reportSpy = vi.spyOn(versionController, 'report');

		vi.stubGlobal(
			'fetch',
			async () =>
				new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } })
		);

		await client.get({ url: '/api/anything' });

		expect(reportSpy).not.toHaveBeenCalled();
	});

	it('calls report() on non-200 responses that carry the header', async () => {
		const reportSpy = vi.spyOn(versionController, 'report');

		vi.stubGlobal(
			'fetch',
			async () =>
				new Response('{}', {
					status: 422,
					headers: { 'Content-Type': 'application/json', 'App-Version': '2.0.0' }
				})
		);

		await client.get({ url: '/api/anything' });

		expect(reportSpy).toHaveBeenCalledWith('2.0.0');
	});
});
