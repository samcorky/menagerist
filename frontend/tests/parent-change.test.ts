import { describe, expect, it } from 'vitest';
import { parentChangeQuestion } from '$lib/parent-change';

const plan = (over: Partial<Parameters<typeof parentChangeQuestion>[0]> = {}) => ({
	parent: null,
	previous: null,
	allowed: true,
	reason: null,
	clashes: [],
	merged: [],
	conflicts: [],
	kept: [],
	archived: [],
	items: 0,
	...over
});

describe('parentChangeQuestion', () => {
	it('asks nothing when the parent does not change', () => {
		expect(parentChangeQuestion(plan({ parent: 'memo', previous: 'memo' }))).toEqual({
			kind: 'none'
		});
		expect(parentChangeQuestion(plan())).toEqual({ kind: 'none' });
	});

	it('asks nothing for a clean attach with no shared fields', () => {
		expect(parentChangeQuestion(plan({ parent: 'memo' }))).toEqual({ kind: 'none' });
	});

	it('asks whether to merge when both define the same fields', () => {
		const question = parentChangeQuestion(
			plan({ parent: 'memo', clashes: ['condition', 'value'], allowed: false })
		);
		expect(question).toEqual({ kind: 'merge', fields: ['condition', 'value'] });
	});

	it('refuses, with the reason, when a shared field is a different kind of field', () => {
		const question = parentChangeQuestion(
			plan({
				parent: 'memo',
				clashes: ['condition'],
				conflicts: ['condition'],
				allowed: false,
				reason: "'poster' has fields its parent type 'memo' has as a different kind of field"
			})
		);
		expect(question.kind).toBe('blocked');
		expect(question).toMatchObject({ fields: ['condition'] });
	});

	it('asks what to do with the parent`s fields when a type loses its parent', () => {
		const question = parentChangeQuestion(plan({ previous: 'memo', kept: ['condition', 'value'] }));
		expect(question).toEqual({ kind: 'detach', fields: ['condition', 'value'], items: 0 });
	});

	it('asks nothing on losing a parent that had no fields', () => {
		expect(parentChangeQuestion(plan({ previous: 'memo' }))).toEqual({ kind: 'none' });
	});

	it('asks the detach question first when a move also clashes with the new parent', () => {
		const question = parentChangeQuestion(
			plan({
				previous: 'memo',
				parent: 'merch',
				kept: ['condition', 'value'],
				clashes: ['condition'],
				allowed: false
			})
		);
		expect(question).toMatchObject({ kind: 'move', merge: ['condition'] });
	});

	it('carries the number of items, since none of them change', () => {
		const question = parentChangeQuestion(
			plan({ previous: 'memo', kept: ['condition'], items: 12 })
		);
		expect(question).toMatchObject({ kind: 'detach', items: 12 });
	});
});
