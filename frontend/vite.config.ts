import tailwindcss from '@tailwindcss/vite';
import { fileURLToPath } from 'node:url';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	resolve: {
		// Mirrors svelte.config.js's kit alias; Vite (and vitest) need it too.
		alias: { $shared: fileURLToPath(new URL('../shared', import.meta.url)) }
	},
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
			// Overridden by the e2e suite so it can run beside a dev stack on :8000.
			'/api': process.env.MENAGERIST_API_PROXY_TARGET ?? 'http://localhost:8000'
		}
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
