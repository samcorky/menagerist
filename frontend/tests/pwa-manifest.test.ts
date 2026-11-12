// The installable-app links in app.html and the icons they point at. The manifest itself is
// served by the backend, and tests/e2e/pwa.spec.ts checks it and the icons it names.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { THEME_COLOURS } from '$lib/theme.svelte';

const STATIC = fileURLToPath(new URL('../static/', import.meta.url));
const APP_HTML = readFileSync(fileURLToPath(new URL('../src/app.html', import.meta.url)), 'utf8');

/** Width and height from a PNG's IHDR chunk. */
function pngSize(file: string): string {
	const png = readFileSync(file);
	expect(png.subarray(1, 4).toString('ascii'), `${file} is a PNG`).toBe('PNG');
	return `${png.readUInt32BE(16)}x${png.readUInt32BE(20)}`;
}

describe('app.html', () => {
	it('links the manifest and the iOS home screen icon', () => {
		expect(APP_HTML).toContain('<link rel="manifest" href="/manifest.webmanifest" />');
		expect(APP_HTML).toContain('<link rel="apple-touch-icon" href="/apple-touch-icon.png" />');
		expect(pngSize(STATIC + 'apple-touch-icon.png')).toBe('180x180');
	});

	it('starts with the light theme colour and switches to the dark one on first paint', () => {
		expect(APP_HTML).toContain(`<meta name="theme-color" content="${THEME_COLOURS.light}" />`);
		expect(APP_HTML).toContain(`dark ? '${THEME_COLOURS.dark}' : '${THEME_COLOURS.light}'`);
	});

	it('marks the site as installable as a standalone app on iOS and Android', () => {
		for (const name of [
			'mobile-web-app-capable',
			'apple-mobile-web-app-capable',
			'apple-mobile-web-app-title',
			'apple-mobile-web-app-status-bar-style'
		]) {
			expect(APP_HTML, name).toContain(`<meta name="${name}"`);
		}
	});
});
