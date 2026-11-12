import adapter from '@sveltejs/adapter-static';
import { fileURLToPath } from 'node:url';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

const config = {
	preprocess: vitePreprocess(),

	compilerOptions: {
		// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
		runes: ({ filename }) =>
			filename && filename.split(/[/\\]/).includes('node_modules') ? undefined : true
	},

	kit: {
		// Registered by hand in the root layout (lib/service-worker-client.ts), so an update
		// waits for the person instead of replacing the page under them.
		serviceWorker: { register: false },
		// Data shared with the backend. Resolves to repo/shared locally and /shared in Docker.
		alias: {
			$shared: fileURLToPath(new URL('../shared', import.meta.url))
		},
		prerender: {
			// The manifest is served by the backend, so the crawler cannot find it in the
			// build. Every other broken link still fails the build.
			handleHttpError: ({ path, message }) => {
				if (path === '/manifest.webmanifest') return;
				throw new Error(message);
			}
		},
		adapter: adapter({
			pages: 'build',
			assets: 'build',
			// Distinct from index.html - otherwise the SPA-fallback shell
			// (needed for dynamic routes like /node/[id]) overwrites the
			// real prerendered root page, since both would write to the same
			// filename. nginx (or any static host) just needs to serve this
			// for any path that doesn't match a prerendered file.
			fallback: '200.html',
			strict: true,
			// Writes a .br and .gz beside each file at build time; the backend serves
			// them to clients that accept them (see backend spa.py), so the SPA costs
			// no CPU per request.
			precompress: true
		})
	}
};

export default config;
