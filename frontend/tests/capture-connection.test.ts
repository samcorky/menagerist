import { describe, expect, it } from 'vitest';
import type { EdgeTypeResponse } from '$lib/api/client';
import { connectionBody, connectionChoices } from '$lib/capture-connection';

const type = (
	slug: string,
	label: string,
	reverse_label: string | null,
	source_types: string[] = [],
	target_types: string[] = []
) => ({ slug, label, reverse_label, source_types, target_types }) as EdgeTypeResponse;

describe('connectionChoices', () => {
	it('offers both readings of a type with a reverse label', () => {
		expect(connectionChoices([type('stored-in', 'Stored in', 'Contains')])).toEqual([
			{
				key: 'stored-in:forward',
				typeSlug: 'stored-in',
				reverse: false,
				label: 'Stored in',
				pickedTypes: []
			},
			{
				key: 'stored-in:reverse',
				typeSlug: 'stored-in',
				reverse: true,
				label: 'Contains',
				pickedTypes: []
			}
		]);
	});

	describe('with the new item type', () => {
		// A book is stored in a box: the book is the source, the box the target.
		const storedIn = type('stored-in', 'Stored in', 'Contains', ['book'], ['box']);

		it('keeps the forward reading for an item the source end allows', () => {
			const choices = connectionChoices([storedIn], 'book');
			expect(choices.map((c) => [c.key, c.pickedTypes])).toEqual([['stored-in:forward', ['box']]]);
		});

		it('keeps the reverse reading for an item the target end allows', () => {
			const choices = connectionChoices([storedIn], 'box');
			expect(choices.map((c) => [c.key, c.pickedTypes])).toEqual([['stored-in:reverse', ['book']]]);
		});

		it('drops a type neither end allows, and every limited one for an untyped item', () => {
			expect(connectionChoices([storedIn], 'film')).toEqual([]);
			expect(connectionChoices([storedIn], null)).toEqual([]);
		});

		it('keeps unlimited types for an untyped item', () => {
			const related = type('related', 'Related to', null);
			expect(connectionChoices([related, storedIn], null).map((c) => c.key)).toEqual([
				'related:forward'
			]);
		});
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
