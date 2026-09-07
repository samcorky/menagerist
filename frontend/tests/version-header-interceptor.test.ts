import { describe, it, expect, vi, beforeEach } from 'vitest';
import '../src/lib/api/client'; // register interceptor side-effects
import { client } from '$lib/api/generated/client.gen';
import { versionController } from '$lib/version.svelte';

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

	it('uses PEP 440 ordering when deciding whether the backend is newer', () => {
		versionController.mismatch = { frontend: '2.0.0', backend: '2.0.0rc1' };
		expect(versionController.backendNewer).toBe(false);

		versionController.mismatch = { frontend: '2.0.0', backend: '2.0.0.post1' };
		expect(versionController.backendNewer).toBe(true);

		versionController.mismatch = { frontend: '2.0.0', backend: '1.9.0' };
		expect(versionController.backendNewer).toBe(false);

		versionController.mismatch = { frontend: '2.0.0', backend: '2.0.0' };
		expect(versionController.backendNewer).toBe(false);

		versionController.mismatch = { frontend: '2.0.0', backend: 'invalid-tag' };
		expect(versionController.backendNewer).toBe(false);
	});

	it('report() ignores matching backend versions and records mismatched ones', () => {
		versionController.report('2.0.0');
		expect(versionController.mismatch).toBeNull();

		versionController.report('2.1.0');
		expect(versionController.mismatch).toEqual({ frontend: '2.0.0', backend: '2.1.0' });

		// Does not overwrite existing mismatch
		versionController.report('2.2.0');
		expect(versionController.mismatch).toEqual({ frontend: '2.0.0', backend: '2.1.0' });
	});

	it('report() handles unparseable versions gracefully', () => {
		versionController.report('invalid-version');
		expect(versionController.mismatch).toEqual({ frontend: '2.0.0', backend: 'invalid-version' });
		expect(versionController.backendNewer).toBe(false);
	});
});
