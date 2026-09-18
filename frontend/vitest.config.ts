import { svelte } from '@sveltejs/vite-plugin-svelte';
import { defineConfig } from 'vitest/config';
import { fileURLToPath } from 'node:url';

export default defineConfig({
	plugins: [svelte()],
	resolve: {
		alias: {
			$lib: fileURLToPath(new URL('./src/lib', import.meta.url)),
			// Vitest's Node/SSR transform has no browser-style dep pre-bundling,
			// so importing the real @lucide/svelte barrel (thousands of icons)
			// here adds well over a minute per run - see tests/mocks/lucide-svelte.ts.
			'@lucide/svelte': fileURLToPath(new URL('./tests/mocks/lucide-svelte.ts', import.meta.url)),
			'bits-ui': fileURLToPath(new URL('./tests/mocks/bits-ui.ts', import.meta.url))
		}
	},
	test: {
		environment: 'node',
		include: ['tests/**/*.test.ts'],
		globals: true,
		setupFiles: ['tests/setup.ts']
	}
});
