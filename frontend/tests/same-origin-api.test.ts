import { readdirSync, readFileSync } from 'node:fs';
import { join, relative, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { afterEach, describe, expect, it, vi } from 'vitest';

// The backend's CORS and CSRF rules assume the browser only ever talks to one origin: the SPA
// calls a relative `/api/...`, in production through the backend itself and in development
// through the Vite proxy. These tests fail if that stops being true.
const root = fileURLToPath(new URL('..', import.meta.url));

function sourceFiles(dir: string): string[] {
	return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
		const path = join(dir, entry.name);
		if (entry.isDirectory()) return entry.name === 'generated' ? [] : sourceFiles(path);
		return /\.(ts|svelte)$/.test(entry.name) ? [path] : [];
	});
}

afterEach(() => {
	vi.unstubAllGlobals();
	vi.resetModules();
});

describe('same-origin API calls', () => {
	it('uses a relative base URL in the browser', async () => {
		vi.stubGlobal('window', {});
		vi.resetModules();

		const { client } = await import('../src/lib/api/client');

		expect(client.getConfig().baseUrl).toBe('');
	});

	it('proxies /api to the backend in the Vite dev server', () => {
		const config = readFileSync(join(root, 'vite.config.ts'), 'utf8');

		expect(config).toMatch(/proxy:\s*\{[^}]*'\/api'\s*:/s);
	});

	it('hard-codes no backend address outside the Node fallback in the client', () => {
		const offenders = sourceFiles(join(root, 'src'))
			.filter((file) => /https?:\/\/(localhost|127\.0\.0\.1)/.test(readFileSync(file, 'utf8')))
			.map((file) => relative(root, file).split(sep).join('/'));

		expect(offenders).toEqual(['src/lib/api/client.ts']);
	});
});
