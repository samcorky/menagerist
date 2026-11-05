// iOS Safari zooms the page when a text field or select under 16px gets focus, and does not zoom back.
// Form controls therefore use 16px on phones and drop to the compact size from `md` up.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const UI = fileURLToPath(new URL('../src/lib/components/ui/', import.meta.url));

const CONTROLS = [
	'input/input.svelte',
	'textarea/textarea.svelte',
	'native-select/native-select.svelte',
	'command/command-input.svelte'
];

describe('form control text size', () => {
	it.each(CONTROLS)('%s is 16px on phones and compact from md', (file) => {
		const source = readFileSync(UI + file, 'utf8');
		expect(source).toMatch(/(?<![:\w-])text-base\b/);
		expect(source).toContain('md:text-sm');
		expect(source).not.toMatch(/(?<![:\w-])text-sm\b/);
	});
});
