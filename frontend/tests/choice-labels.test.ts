import { describe, it, expect } from 'vitest';
import { render } from 'svelte/server';
import ChoiceInput from '../src/lib/field-types/choice/ChoiceInput.svelte';
import { optionLabel } from '../src/lib/field-types/choice/stale-choice';
import type { JsonSchemaProperty } from '../src/lib/schema-types';

const labelled = {
	type: 'string',
	enum: ['stable', 'preview'],
	'x-menagerist': { display: 'radio', labels: { stable: 'Stable', preview: 'Preview' } }
} as unknown as JsonSchemaProperty;

describe('optionLabel', () => {
	it('reads the declared label for a stored value', () => {
		expect(optionLabel({ monday: 'Monday' }, 'monday')).toBe('Monday');
	});

	it('falls back to the stored value when there is no label', () => {
		expect(optionLabel(undefined, 'Mint')).toBe('Mint');
		expect(optionLabel({ monday: 'Monday' }, 'sunday')).toBe('sunday');
	});
});

describe('ChoiceInput labels', () => {
	it('shows each option by its label but keeps the stored value', () => {
		const body = render(ChoiceInput, {
			props: { value: 'stable', onChange: () => {}, ariaLabel: 'Channel', prop: labelled }
		}).body.replace(/\s+/g, ' ');

		expect(body).toMatch(/value="stable"[^>]*checked[^>]*>(<!---->)? ?Stable/);
		expect(body).toMatch(/value="preview"[^>]*>(<!---->)? ?Preview/);
		expect(body).not.toMatch(/> ?(stable|preview) ?</);
	});
});
