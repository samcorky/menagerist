// A plain <option> takes its colours from the select, not the theme, so in dark mode on desktop the
// browser-drawn list can show dark text on a dark background. NativeSelectOption sets the system
// colours that follow color-scheme, so every option in the app goes through it.
import { describe, expect, it } from 'vitest';
import { readdirSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { join, relative } from 'node:path';

const SRC = fileURLToPath(new URL('../src/', import.meta.url));

// The wrapper renders the real element, and the calendar's month and year pickers style their own
// (bits-ui hands them a bare <select>). Suggestions are options of a <datalist>, not a select: the
// browser draws them in its own colours.
const ALLOWED = [
	'lib/components/ui/native-select/',
	'lib/components/ui/calendar/',
	'lib/components/suggest-input.svelte'
];

function svelteFiles(dir: string): string[] {
	return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
		const path = join(dir, entry.name);
		if (entry.isDirectory()) return svelteFiles(path);
		return entry.name.endsWith('.svelte') ? [path] : [];
	});
}

describe('native select options', () => {
	it('use NativeSelectOption, not a plain <option>', () => {
		const offenders = svelteFiles(SRC)
			.map((file) => relative(SRC, file).replaceAll('\\', '/'))
			.filter((file) => !ALLOWED.some((prefix) => file.startsWith(prefix)))
			.filter((file) => /<option[\s>]/.test(readFileSync(join(SRC, file), 'utf8')));
		expect(offenders).toEqual([]);
	});
});
