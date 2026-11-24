import { describe, expect, it } from 'vitest';
import type { EdgeTypeResponse } from '$lib/api/client';
import { connectionBody, connectionChoices } from '$lib/capture-connection';

const type = (slug: string, label: string, reverse_label: string | null) =>
	({ slug, label, reverse_label }) as EdgeTypeResponse;

describe('connectionChoices', () => {
	it('offers both readings of a type with a reverse label', () => {
		expect(connectionChoices([type('stored-in', 'Stored in', 'Contains')])).toEqual([
			{ key: 'stored-in:forward', typeSlug: 'stored-in', reverse: false, label: 'Stored in' },
			{ key: 'stored-in:reverse', typeSlug: 'stored-in', reverse: true, label: 'Contains' }
		]);
	});

	it('offers one reading when both ends read the same', () => {
		const choices = connectionChoices([type('related', 'Related to', null)]);
		expect(choices.map((c) => c.key)).toEqual(['related:forward']);
	});

	it('is empty without connection types', () => {
		expect(connectionChoices([])).toEqual([]);
	});
});

describe('connectionBody', () => {
	const [forward, reverse] = connectionChoices([type('stored-in', 'Stored in', 'Contains')]);

	it('runs from the new item to the picked one', () => {
		expect(connectionBody(forward, 'new', 'box')).toEqual({
			source_id: 'new',
			target_ids: ['box'],
			type: 'stored-in',
			reverse: false
		});
	});

	it('runs back from the picked item for a reverse reading', () => {
		expect(connectionBody(reverse, 'new', 'box').reverse).toBe(true);
	});
});
