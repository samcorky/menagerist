import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

const config = {
	preprocess: vitePreprocess(),

	compilerOptions: {
		// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
		runes: ({ filename }) =>
			filename && filename.split(/[/\\]/).includes('node_modules') ? undefined : true
	},

	kit: {
		adapter: adapter({
			pages: 'build',
			assets: 'build',
			// Distinct from index.html - otherwise the SPA-fallback shell
			// (needed for dynamic routes like /node/[id]) overwrites the
			// real prerendered root page, since both would write to the same
			// filename. nginx (or any static host) just needs to serve this
			// for any path that doesn't match a prerendered file.
			fallback: '200.html',
			strict: true
		})
	}
};

export default config;
