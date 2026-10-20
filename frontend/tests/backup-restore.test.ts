import { afterEach, describe, expect, it, vi } from 'vitest';
import { restoreFirstRunArchive } from '../src/lib/backup-restore';

afterEach(() => vi.unstubAllGlobals());

describe('first-run backup restore', () => {
	it('uploads the file bytes directly and accepts an empty success response', async () => {
		const file = new File(['archive bytes'], 'backup.tar.gz', { type: 'application/gzip' });
		let sent: Request | undefined;
		vi.stubGlobal('fetch', async (request: Request) => {
			sent = request;
			return new Response(null, { status: 204 });
		});
		expect(await restoreFirstRunArchive(file)).toEqual({ ok: true });
		expect(sent?.url).toContain('/api/v1/backup/first-run-restore');
		expect(sent?.headers.get('Content-Type')).toBe('application/gzip');
		expect(await sent?.text()).toBe('archive bytes');
	});

	it.each([
		[400, 'verified'],
		[409, 'version'],
		[413, 'larger'],
		[429, 'Wait'],
		[500, 'try again']
	])('gives a recovery message for %s', async (status, message) => {
		vi.stubGlobal(
			'fetch',
			async () => new Response('{}', { status, headers: { 'Content-Type': 'application/json' } })
		);
		const result = await restoreFirstRunArchive(new File(['bytes'], 'backup.tar.gz'));
		expect(result.ok).toBe(false);
		if (!result.ok) expect(result.message).toContain(message);
	});

	it('explains a network failure without exposing the exception', async () => {
		vi.stubGlobal('fetch', async () => {
			throw new Error('internal transport details');
		});
		const result = await restoreFirstRunArchive(new File([], 'backup.tar.gz'));
		expect(result.ok).toBe(false);
		if (!result.ok) expect(result.message).toContain('connection');
	});
});
