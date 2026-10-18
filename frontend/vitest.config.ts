import { svelte } from '@sveltejs/vite-plugin-svelte';
import { defineConfig } from 'vitest/config';
import { readdirSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

// Importing modules once per worker (isolate: false) is far faster here, but a file that mocks
// modules, stubs globals or fakes timers would leak into the files after it. Those files are
// detected by what they call and keep full isolation; everything else shares modules.
// Tests must not mutate module-level state without putting it back (see tests/registry.test.ts).
const testsDir = fileURLToPath(new URL('./tests', import.meta.url));
const testFiles = readdirSync(testsDir).filter((f) => f.endsWith('.test.ts'));
const needsIsolation = (file: string) =>
	/\bvi\.(mock|doMock|stubGlobal|stubEnv|resetModules|useFakeTimers)\b|\bglobalThis\./.test(
		readFileSync(`${testsDir}/${file}`, 'utf8')
	);
const isolated = testFiles.filter(needsIsolation).map((f) => `tests/${f}`);
const shared = testFiles.filter((f) => !needsIsolation(f)).map((f) => `tests/${f}`);

export default defineConfig({
	plugins: [svelte()],
	resolve: {
		alias: [
			{ find: '$lib', replacement: fileURLToPath(new URL('./src/lib', import.meta.url)) },
			{ find: '$shared', replacement: fileURLToPath(new URL('../shared', import.meta.url)) },
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
		globals: true,
		setupFiles: ['tests/setup.ts'],
		projects: [
			{ extends: true, test: { name: 'shared', include: shared, isolate: false } },
			{ extends: true, test: { name: 'isolated', include: isolated, isolate: true } }
		]
	}
});
