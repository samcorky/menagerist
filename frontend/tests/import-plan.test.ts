import { describe, expect, it } from 'vitest';
import { countOf, kindName, summarisePlan, type ImportPlan } from '$lib/import-plan';

function entity(
	kind: string,
	label: string,
	action: 'create' | 'unchanged' | 'skip' | 'conflict' | 'ambiguous' = 'create',
	over: Partial<ImportPlan['entities'][number]> = {}
) {
	return {
		kind,
		ref: label.toLowerCase(),
		label,
		action,
		reason: null,
		changed: [],
		deleted: false,
		...over
	};
}

function plan(over: Partial<ImportPlan> = {}): ImportPlan {
	return { ready: true, blockers: [], entities: [], ...over };
}

describe('kindName and countOf', () => {
	it('uses collector-facing names, singular or plural', () => {
		expect(kindName('item_type', 1)).toBe('item type');
		expect(kindName('relationship_type', 2)).toBe('connection types');
		expect(countOf('preset', 3)).toBe('3 saved items');
	});

	it('stays neutral about a kind it does not know', () => {
		expect(kindName('mystery', 1)).toBe('thing');
		expect(kindName('mystery', 2)).toBe('things');
	});
});

describe('summarisePlan', () => {
	it('groups what would be added by kind, in a fixed order', () => {
		const summary = summarisePlan(
			plan({
				entities: [entity('item', 'Ada'), entity('preset', 'Grades'), entity('item', 'Bob')]
			})
		);

		expect(summary.adding.map((g) => g.heading)).toEqual(['1 saved item', '2 items']);
		expect(summary.adding[1].names).toEqual(['Ada', 'Bob']);
		expect(summary.canAdd).toBe(true);
	});

	it('lists a few names and counts the rest', () => {
		const items = ['a', 'b', 'c', 'd', 'e', 'f', 'g'].map((n) => entity('item', n));

		const [group] = summarisePlan(plan({ entities: items })).adding;

		expect(group.names).toHaveLength(5);
		expect(group.more).toBe(2);
	});

	it('only counts connections and covers', () => {
		const summary = summarisePlan(
			plan({ entities: [entity('connection', 'A to B'), entity('cover', 'A')] })
		);

		expect(summary.adding.map((g) => [g.heading, g.names, g.more])).toEqual([
			['1 connection', [], 0],
			['1 cover', [], 0]
		]);
	});

	it('separates what you have from what is in the way', () => {
		const summary = summarisePlan(
			plan({
				ready: false,
				blockers: [{ code: 'RequirementsNotMetError', reason: 'Add Vinyl first.' }],
				entities: [
					entity('preset', 'Grades', 'unchanged'),
					entity('item_type', 'Album', 'conflict')
				]
			})
		);

		expect(summary.have.map((e) => e.label)).toEqual(['Grades']);
		expect(summary.conflicts.map((e) => e.label)).toEqual(['Album']);
		expect(summary.blockers).toHaveLength(1);
		expect(summary.canAdd).toBe(false);
	});

	it('offers nothing to add when you already have it all', () => {
		const summary = summarisePlan(plan({ entities: [entity('preset', 'Grades', 'unchanged')] }));

		expect(summary.adding).toEqual([]);
		expect(summary.canAdd).toBe(false);
	});

	it('sorts a kind it does not know last', () => {
		const summary = summarisePlan(
			plan({ entities: [entity('mystery', 'X'), entity('item', 'Ada')] })
		);

		expect(summary.adding.map((g) => g.kind)).toEqual(['item', 'mystery']);
	});
});

describe('summarisePlan for an import done before', () => {
	it('lists what is left out with its reasons, ambiguous or skipped', () => {
		const summary = summarisePlan(
			plan({
				entities: [
					entity('item', 'Ada', 'skip', { reason: 'No key.' }),
					entity('item', 'Rick', 'ambiguous', { reason: 'Two of them.' }),
					entity('connection', 'Photo to eBay', 'skip', { reason: 'Left out.' })
				]
			})
		);

		expect(summary.skipped.map((e) => [e.label, e.reason])).toEqual([
			['Ada', 'No key.'],
			['Rick', 'Two of them.'],
			['Photo to eBay', 'Left out.']
		]);
	});

	it('leaves what was deleted after importing to the page that can bring it back', () => {
		const summary = summarisePlan(
			plan({
				entities: [
					entity('item', 'Gone', 'skip', { source_key: '5', deleted: true }),
					entity('item', 'Kept', 'unchanged', { source_key: '7', matched_id: 'x' })
				]
			})
		);

		expect(summary.have.map((e) => e.label)).toEqual(['Kept']);
		expect(summary.skipped).toEqual([]);
	});
});
