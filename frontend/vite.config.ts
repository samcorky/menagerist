import tailwindcss from '@tailwindcss/vite';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

function getBackendVersion(): string {
	try {
		const path = fileURLToPath(new URL('./openapi.json', import.meta.url));
		const schema = JSON.parse(readFileSync(path, 'utf-8')) as { info?: { version?: string } };
		return schema.info?.version ?? '';
	} catch {
		return '';
	}
}

export default defineConfig({
	plugins: [
		tailwindcss(),
		// Passing any options here (compilerOptions, adapter, ...) makes this
		// call ignore svelte.config.js entirely rather than merging with it -
		// so all of that (including compilerOptions.runes and the adapter)
		// lives in svelte.config.js instead, and this call takes none.
		sveltekit()
	],
	server: {
		// Mirrors how nginx proxies `/api/*` to the backend in production, so
		// the frontend always calls a same-origin relative `/api/...` and never
		// needs to know the backend's host/port.
		proxy: {
			'/api': 'http://localhost:8000'
		}
	},
	define: {
		__EXPECTED_BACKEND_VERSION__: JSON.stringify(getBackendVersion())
	},
	optimizeDeps: {
		// @lucide/svelte has thousands of icon exports - if left to be
		// discovered lazily (different routes each importing a few icons),
		// Vite's dep optimizer can re-trigger mid-navigation and cascade into
		// a "504 Outdated Optimize Dep" loop. Pre-bundling it upfront avoids
		// that entirely.
		include: ['@lucide/svelte']
	}
});
