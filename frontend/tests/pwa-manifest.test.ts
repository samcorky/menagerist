// The installable-app files: the manifest, the icons it names and the links in app.html.
import { describe, expect, it } from 'vitest';
import { existsSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { THEME_COLOURS } from '$lib/theme.svelte';

const STATIC = fileURLToPath(new URL('../static/', import.meta.url));
const APP_HTML = readFileSync(fileURLToPath(new URL('../src/app.html', import.meta.url)), 'utf8');

type Icon = { src: string; sizes: string; type: string; purpose?: string };
const manifest = JSON.parse(readFileSync(STATIC + 'manifest.webmanifest', 'utf8')) as {
	id: string;
	name: string;
	short_name: string;
	start_url: string;
	scope: string;
	display: string;
	theme_color: string;
	background_color: string;
	icons: Icon[];
	orientation: string;
	lang: string;
	dir: string;
	categories: string[];
	display_override: string[];
	shortcuts: { name: string; url: string }[];
	screenshots: (Icon & { form_factor: string; label: string })[];
};

/** Width and height from a PNG's IHDR chunk. */
function pngSize(file: string): string {
	const png = readFileSync(file);
	expect(png.subarray(1, 4).toString('ascii'), `${file} is a PNG`).toBe('PNG');
	return `${png.readUInt32BE(16)}x${png.readUInt32BE(20)}`;
}

describe('web app manifest', () => {
	it('names the app and gives it a stable identity at the origin root', () => {
		expect(manifest.name).toBe('Menagerist');
		expect(manifest.short_name).toBe('Menagerist');
		// Instances are served from the origin root; the id and scope must not change once
		// people have installed the app.
		expect(manifest.id).toBe('/');
		expect(manifest.start_url).toBe('/');
		expect(manifest.scope).toBe('/');
		expect(manifest.display).toBe('standalone');
	});

	it('uses the light theme colour for the title bar and splash screen', () => {
		expect(manifest.theme_color).toBe(THEME_COLOURS.light);
		expect(manifest.background_color).toBe(THEME_COLOURS.light);
	});

	it('lists icons that exist and are the size they claim', () => {
		for (const icon of manifest.icons) {
			const file = STATIC + icon.src.replace(/^\//, '');
			expect(existsSync(file), `${icon.src} exists`).toBe(true);
			expect(icon.type).toBe('image/png');
			expect(pngSize(file), icon.src).toBe(icon.sizes);
		}
	});

	it('offers 192 and 512 icons, and a maskable one, as installability needs', () => {
		const any = manifest.icons.filter((i) => i.purpose === 'any').map((i) => i.sizes);
		expect(any).toEqual(expect.arrayContaining(['192x192', '512x512']));
		expect(manifest.icons.some((i) => i.purpose === 'maskable' && i.sizes === '512x512')).toBe(
			true
		);
	});

	it('describes the app for install prompts and app stores', () => {
		expect(manifest.orientation).toBe('any');
		expect(manifest.lang).toBe('en-GB');
		expect(manifest.dir).toBe('ltr');
		expect(manifest.categories.length).toBeGreaterThan(0);
		expect(manifest.display_override[0]).toBe(manifest.display);
	});

	it('offers shortcuts that point at real routes', () => {
		expect(manifest.shortcuts.map((s) => s.url)).toEqual(['/items/new', '/items', '/collections']);
		for (const { url } of manifest.shortcuts) expect(url.startsWith(manifest.scope)).toBe(true);
	});

	it('ships a narrow and a wide screenshot that exist and are the size they claim', () => {
		expect(manifest.screenshots.map((s) => s.form_factor).sort()).toEqual(['narrow', 'wide']);
		for (const shot of manifest.screenshots) {
			const file = STATIC + shot.src.replace(/^\//, '');
			expect(existsSync(file), `${shot.src} exists`).toBe(true);
			expect(shot.type).toBe('image/png');
			expect(pngSize(file), shot.src).toBe(shot.sizes);
			expect(shot.label.length).toBeGreaterThan(0);
		}
	});
});

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
