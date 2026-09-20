import { svelte } from '@sveltejs/vite-plugin-svelte';
import { defineConfig } from 'vitest/config';
import { fileURLToPath } from 'node:url';

export default defineConfig({
	plugins: [svelte()],
	resolve: {
		alias: [
			{ find: '$lib', replacement: fileURLToPath(new URL('./src/lib', import.meta.url)) },
			// Vitest's Node/SSR transform has no browser-style dep pre-bundling,
			// so importing the real @lucide/svelte barrel (thousands of icons)
			// here adds well over a minute per run - see tests/mocks/lucide-svelte.ts.
			// The regex alias catches subpath imports like @lucide/svelte/icons/chevron-down.
			{
				find: /^@lucide\/svelte\/icons\/.+$/,
				replacement: fileURLToPath(new URL('./tests/mocks/lucide-icon-stub.ts', import.meta.url))
			},
			{
				find: '@lucide/svelte',
				replacement: fileURLToPath(new URL('./tests/mocks/lucide-svelte.ts', import.meta.url))
			},
			{
				find: 'bits-ui',
				replacement: fileURLToPath(new URL('./tests/mocks/bits-ui.ts', import.meta.url))
			}
		]
	},
	test: {
		environment: 'node',
		include: ['tests/**/*.test.ts'],
		globals: true,
		setupFiles: ['tests/setup.ts']
	}
});
