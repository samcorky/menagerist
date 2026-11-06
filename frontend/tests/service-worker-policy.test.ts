import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import {
	CACHE_PREFIX,
	OFFLINE_URL,
	SHELL_FILES,
	cacheName,
	routeFor,
	staleCaches
} from '$lib/service-worker/policy';

const ORIGIN = 'https://menagerist.example';
const PRECACHED = new Set(['/_app/immutable/entry/app.abc.js', ...SHELL_FILES]);
const get = (path: string, mode = 'cors', method = 'GET') => ({
	method,
	mode,
	url: ORIGIN + path
});

describe('routeFor', () => {
	it('answers the build files and the offline page from the cache', () => {
		expect(routeFor(get('/_app/immutable/entry/app.abc.js'), ORIGIN, PRECACHED)).toBe('asset');
		expect(routeFor(get(OFFLINE_URL, 'navigate'), ORIGIN, PRECACHED)).toBe('asset');
	});

	it('asks the network first for page loads', () => {
		expect(routeFor(get('/items', 'navigate'), ORIGIN, PRECACHED)).toBe('navigation');
		expect(routeFor(get('/admin/settings', 'navigate'), ORIGIN, PRECACHED)).toBe('navigation');
	});

	it('never touches the API, whatever asks for it', () => {
		for (const mode of ['cors', 'navigate', 'same-origin']) {
			expect(routeFor(get('/api/node/123', mode), ORIGIN, PRECACHED)).toBe('network');
		}
		expect(routeFor(get('/api/auth/me'), ORIGIN, PRECACHED)).toBe('network');
		expect(routeFor(get('/api'), ORIGIN, PRECACHED)).toBe('network');
	});

	it('leaves uploads, media and other requests to the network', () => {
		expect(routeFor(get('/api/media/abc/original'), ORIGIN, PRECACHED)).toBe('network');
		expect(routeFor(get('/some/image.png', 'no-cors'), ORIGIN, PRECACHED)).toBe('network');
	});

	it('only handles GET on its own origin', () => {
		expect(routeFor(get('/items', 'navigate', 'POST'), ORIGIN, PRECACHED)).toBe('network');
		const other = { method: 'GET', mode: 'cors', url: 'https://cdn.example/_app/x.js' };
		expect(routeFor(other, ORIGIN, PRECACHED)).toBe('network');
	});
});

describe('caches', () => {
	it('names each version separately so an old page keeps its files until the switch', () => {
		expect(cacheName('1')).toBe(CACHE_PREFIX + '1');
		expect(cacheName('1')).not.toBe(cacheName('2'));
	});

	it('deletes earlier versions and nothing it does not own', () => {
		const names = [cacheName('1'), cacheName('2'), 'something-else', 'workbox-precache'];
		expect(staleCaches(names, cacheName('2'))).toEqual([cacheName('1')]);
	});
});

describe('the offline page', () => {
	const html = readFileSync(
		fileURLToPath(new URL('../static/offline.html', import.meta.url)),
		'utf8'
	);

	it('is listed for precaching and explains the situation', () => {
		expect(SHELL_FILES).toContain(OFFLINE_URL);
		expect(html).toContain("You're offline");
		expect(html).toContain('Try again');
	});

	it('needs nothing else from the network', () => {
		expect(html).not.toMatch(/<script[^>]*\ssrc=|<link[^>]*rel="stylesheet"|<img|url\(/);
	});
});
