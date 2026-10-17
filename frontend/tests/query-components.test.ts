// Server-renders the filter builder's components (the `$effect`-free parts) to check what
// they show. Interaction is covered by the pure tests in query-builder.test.ts.
import { describe, expect, it, vi } from 'vitest';
import type { ComponentProps } from 'svelte';
import { render } from 'svelte/server';

vi.mock('@lucide/svelte', async () => {
	const Noop = (await import('./mocks/noop.svelte')).default;
	return { X: Noop, TriangleAlert: Noop, Plus: Noop, FolderPlus: Noop, ChevronDown: Noop };
});
vi.mock('@lucide/svelte/icons/chevron-down', async () => ({
	default: (await import('./mocks/noop.svelte')).default
}));
vi.mock('$lib/field-types/date/DateInput.svelte', async () => ({
	default: (await import('./mocks/noop.svelte')).default
}));
vi.mock('$lib/components/ui/responsive-dialog/index.js', async () => {
	const Passthrough = (await import('./mocks/passthrough.svelte')).default;
	return { Root: Passthrough, Content: Passthrough, Description: Passthrough };
});

import QueryBuilder from '$lib/components/query-builder.svelte';
import QueryChips from '$lib/components/query-chips.svelte';
import QueryConditionRow from '$lib/components/query-condition-row.svelte';
import QueryValueInput from '$lib/components/query-value-input.svelte';
import {
	ARCHIVED_FIELD_MESSAGE,
	conditionFor,
	fieldSubject,
	itemFieldPickerItems,
	missingItemFieldPaths,
	NO_ITEM_FIELD_MESSAGE,
	STALE_FIELD_MESSAGE,
	withSubject,
	type BuilderView
} from '$lib/query/builder';
import { BuilderState } from '$lib/query/builder-state.svelte';
import { formatIsoDate } from '$lib/format-date';
import { describeCondition } from '$lib/query/summary';
import { buildCatalogue, summaryLookup } from '$lib/query/fields';
import type { Condition, Query } from '$lib/query/types';
import { filterComboboxItems } from '$lib/components/ui/combobox/combobox';
import { catalogue, itemTypes, stubView } from './query-builder-fixtures';

const valueInput = (condition: Condition) =>
	render(QueryValueInput, {
		props: { condition, name: 'Condition 1', view: stubView(), onchange: () => {} }
	}).body;

const valueInput2 = (condition: Condition) =>
	render(QueryValueInput, {
		props: {
			condition,
			name: 'Condition 1',
			view: stubView({
				catalogue: buildCatalogue(itemTypes, true, [
					{ key: 'signed', kind: 'boolean', label: 'Signed', count: 2 },
					{ key: 'mood', kind: 'choice', label: 'Mood', count: 1 },
					{ key: 'tags', kind: 'multichoice', label: 'Moods', count: 1 }
				])
			}),
			onchange: () => {}
		}
	}).body;

const inputs = (html: string) => html.match(/<input\b/g)?.length ?? 0;

describe('query-value-input', () => {
	it('renders two inputs for between', () => {
		const html = valueInput({
			kind: 'field',
			type: 'film',
			key: 'stock',
			op: 'between',
			value: [1, 5]
		});
		expect(inputs(html)).toBe(2);
		expect(html).toContain('aria-label="Condition 1, value from"');
		expect(html).toContain('aria-label="Condition 1, value to"');
	});

	it('offers comparing with another field only for comparable kinds', () => {
		const text = valueInput({ kind: 'field', type: 'film', key: 'note', op: '=', value: 'x' });
		expect(text).not.toContain('Compare with another field');
		const number = valueInput({ kind: 'field', type: 'film', key: 'stock', op: '<=', value: 3 });
		expect(number).toContain('Compare with another field');
	});

	it('shows the other field when comparing with one', () => {
		const html = valueInput({
			kind: 'field',
			type: 'film',
			key: 'stock',
			op: '<=',
			value: { ref: 'reorder_at' }
		});
		expect(html).toContain('aria-label="Condition 1, value, other field"');
		expect(html).toContain('Reorder at');
		expect(html).toMatch(
			/<button[^>]*role="combobox"[^>]*aria-label="Condition 1, value, other field"/
		);
	});

	it('keeps a vanished other field selected and flagged', () => {
		const html = valueInput({
			kind: 'field',
			type: 'film',
			key: 'stock',
			op: '<=',
			value: { ref: 'gone' }
		});
		expect(html).toContain('gone (no longer exists)');
	});

	it.each<Condition>([
		{ kind: 'field', type: 'film', key: 'stock', op: '>', value: 'abc' },
		{ kind: 'field', type: 'film', key: 'price', op: '>', value: 3 },
		{ kind: 'field', type: 'film', key: 'runtime', op: '>', value: { rel: '-1d' } },
		{ kind: 'field', type: 'film', key: 'stock', op: 'between', value: 3 },
		{ kind: 'field', type: 'film', key: 'format', op: 'in', value: 'DVD' },
		{ kind: 'field', type: 'film', key: 'seen', op: '=', value: 'maybe' },
		{ kind: 'field', type: 'film', key: 'note', op: 'in', value: [1, 2] },
		{ kind: 'field', type: 'film', key: 'gone', op: '=', value: { value: 1, currency: 'GBP' } },
		{ kind: 'date', on: 'created', op: 'between', value: 'nonsense' }
	])('renders a value of the wrong type without throwing: %j', (condition) => {
		expect(() => valueInput(condition)).not.toThrow();
	});

	it('keeps a number that is not a number visible to fix', () => {
		const html = valueInput({ kind: 'field', type: 'film', key: 'stock', op: '>', value: 'abc' });
		expect(html).toContain('value="abc"');
	});

	it('offers the field options for "is one of"', () => {
		const html = valueInput({
			kind: 'field',
			type: 'film',
			key: 'format',
			op: 'in',
			value: ['DVD']
		});
		expect(html).toContain('Blu-ray');
		expect(html).toMatch(/aria-pressed="true"[^>]*>\s*DVD/);
	});

	it('offers the field options for "is not one of"', () => {
		const html = valueInput({
			kind: 'field',
			type: 'film',
			key: 'format',
			op: 'not_in',
			value: ['DVD']
		});
		expect(html).toContain('Blu-ray');
		expect(html).toMatch(/aria-pressed="true"[^>]*>\s*DVD/);
	});

	it('takes a typed list for "is not one of" on text', () => {
		const html = valueInput({
			kind: 'field',
			type: 'film',
			key: 'note',
			op: 'not_in',
			value: ['a', 'b']
		});
		expect(html).toContain('value="a, b"');
	});
});

describe('query-condition-row', () => {
	const row = (condition: Condition, warned: string[] = []) =>
		render(QueryConditionRow, {
			props: {
				condition,
				path: [1],
				view: stubView({ numbers: new Map([['1', 2]]), warned: new Set(warned) })
			}
		}).body;

	it('names every control with the row number', () => {
		const html = row({ kind: 'field', type: 'film', key: 'stock', op: '>', value: 3 });
		expect(html).toContain('aria-label="Condition 2, field"');
		expect(html).toContain('aria-label="Condition 2, operator"');
		expect(html).toContain('aria-label="Condition 2, value"');
		expect(html).toContain('aria-label="Remove condition 2"');
	});

	it('labels a sub-field with its full path on the picker', () => {
		const html = row({
			kind: 'field',
			type: 'film',
			key: 'cast',
			sub_key: 'role',
			op: '=',
			value: 'x'
		} as Condition);
		expect(html).toContain('Film › Cast › Role');
	});

	it('marks a field the server could not match', () => {
		const html = row({ kind: 'field', type: 'film', key: 'stock', op: '>', value: 3 }, ['1']);
		expect(html).toContain(STALE_FIELD_MESSAGE);
	});

	it('shows a field that no longer exists as such', () => {
		const html = row({ kind: 'field', type: 'film', key: 'gone', op: '>', value: 3 });
		expect(html).toContain('(no longer exists)');
		expect(html).toContain(STALE_FIELD_MESSAGE);
	});

	it('explains a value that does not fit', () => {
		const html = row({ kind: 'field', type: 'film', key: 'stock', op: '>', value: 'abc' });
		expect(html).toContain('Enter a number.');
		expect(html).toContain('The current value “abc” does not fit.');
	});
});

describe('query-chips', () => {
	it('shows formatted descriptions and the warning', () => {
		const query: Query = {
			v: 1,
			where: {
				op: 'and',
				children: [
					{ kind: 'field', type: 'film', key: 'runtime', op: '<=', value: 2700 },
					{ kind: 'field', type: 'film', key: 'gone', op: '=', value: 1 }
				]
			},
			sort: []
		};
		const html = render(QueryChips, {
			props: {
				query,
				lookup: summaryLookup(catalogue),
				warned: new Set(['1']),
				onopen: () => {},
				onremove: () => {},
				onclear: () => {}
			}
		}).body;
		expect(html).toContain('Film: Runtime is at most 45:00');
		expect(html).toContain('aria-label="Remove filter: Film: Runtime is at most 45:00"');
		expect(html).toContain(STALE_FIELD_MESSAGE);
		expect(html).toContain('Clear filters');
	});
});

describe('query-builder', () => {
	const query: Query = {
		v: 1,
		where: {
			op: 'and',
			children: [
				{ kind: 'field', type: 'film', key: 'stock', op: '>', value: 3 },
				{ op: 'or', children: [{ kind: 'favourite', value: true }] }
			]
		},
		sort: []
	};
	const panel = (props: Partial<ComponentProps<typeof QueryBuilder>>) =>
		render(QueryBuilder, {
			props: { open: true, query, catalogue, onchange: () => {}, ...props }
		}).body;

	it('shows the server detail inline, against the row it names', () => {
		const html = panel({
			error: { message: 'That value does not fit a number field.', path: [0] }
		});
		expect(html).toContain('Condition 1: That value does not fit a number field.');
	});

	it('shows match all / any and the rows', () => {
		const html = panel({});
		expect(html).toContain('Filters');
		expect(html).toContain('aria-label="All conditions: match all or any"');
		expect(html).toContain('aria-label="Condition 2, field"');
		expect(html).toContain('Sort by');
	});

	it('disables adding conditions at the limit, with a hint', () => {
		const full: Query = {
			v: 1,
			where: {
				op: 'and',
				children: Array.from({ length: 50 }, (): Condition => ({ kind: 'favourite', value: true }))
			},
			sort: []
		};
		const html = panel({ query: full });
		const addButton = html.match(/<button[^>]*data-add-condition[^>]*>/)?.[0] ?? '';
		expect(addButton).toMatch(/\sdisabled/);
		expect(html).toContain('A filter can have up to 50 conditions.');
	});

	it('offers Done when changes apply as you go', () => {
		const html = panel({});
		expect(html).toContain('Done');
		expect(html).not.toContain('>Cancel<');
	});

	it('offers Save and Cancel instead of Done when saving is deliberate', () => {
		const html = panel({
			title: 'Edit conditions',
			description: 'Change the conditions, then choose Save.',
			onsave: () => {},
			oncancel: () => {}
		});
		expect(html).toContain('Edit conditions');
		expect(html).toContain('Change the conditions, then choose Save.');
		expect(html).toContain('>Save<');
		expect(html).toContain('>Cancel<');
		expect(html).not.toContain('Done');
		expect(html).not.toContain('Changes apply as you go');
	});

	it('disables Save and Cancel while saving', () => {
		const html = panel({ onsave: () => {}, oncancel: () => {}, saving: true });
		expect(html).toContain('Saving…');
		const cancel = (html.match(/<button[\s\S]*?<\/button>/g) ?? []).find((b) =>
			b.includes('Cancel')
		);
		expect(cancel).toMatch(/\sdisabled/);
	});

	it('shows the page notice when the page filters do not fit', () => {
		const html = panel({
			notice: 'Too many conditions to add the page filters. Remove a condition.'
		});
		expect(html).toContain('Too many conditions to add the page filters.');
	});

	it('uses a searchable picker for the sort field, keeping the direction native', () => {
		const html = panel({ query: { v: 1, where: null, sort: [] } });
		expect(html).toMatch(/<button[^>]*role="combobox"[^>]*aria-label="Sort by"/);
		expect(html).toMatch(/<select[^>]*aria-label="Sort direction"/);
		expect(html).toContain('Order added (default)');
	});

	it('starts an empty filter with one row to fill in', () => {
		const html = panel({ query: { v: 1, where: null, sort: [] } });
		expect(html).toContain('Choose what to filter on');
	});
});

describe('review fixes', () => {
	const rowHtml = (condition: Condition, overrides: Partial<BuilderView> = {}) =>
		render(QueryConditionRow, {
			props: {
				condition,
				path: [0],
				view: stubView({ numbers: new Map([['0', 1]]), ...overrides })
			}
		}).body;
	const triggerText = (html: string, label: string) =>
		html.match(new RegExp(`<button[^>]*aria-label="${label}"[^>]*>([\\s\\S]*?)</button>`))?.[1] ??
		'';
	const selectedOption = (html: string, label: string) =>
		html.match(new RegExp(`<select[^>]*aria-label="${label}"[^>]*>([\\s\\S]*?)</select>`))?.[1] ??
		'';

	it('shows an archived field as selected and flagged, keeping the row editable', () => {
		const html = rowHtml({ kind: 'field', type: 'film', key: 'old', op: '>', value: 3 });
		expect(html).toMatch(/<button[^>]*role="combobox"[^>]*aria-label="Condition 1, field"/);
		expect(triggerText(html, 'Condition 1, field')).toContain('Film › Old (archived)');
		expect(html).toContain(ARCHIVED_FIELD_MESSAGE);
		expect(html).toContain('aria-label="Condition 1, value"');
		expect(html).toContain('aria-label="Remove condition 1"');
	});

	it('shows a missing field as selected and flagged', () => {
		const html = rowHtml({ kind: 'field', type: 'film', key: 'gone', op: '>', value: 3 });
		expect(triggerText(html, 'Condition 1, field')).toContain('Film › gone (no longer exists)');
		expect(html).toContain(STALE_FIELD_MESSAGE);
	});

	it('does not call fields stale while the item types are loading', () => {
		const html = rowHtml(
			{ kind: 'field', type: 'film', key: 'stock', op: '>', value: 3 },
			{ catalogue: buildCatalogue([], false) }
		);
		expect(html).not.toContain('no longer exists');
		expect(html).not.toContain(STALE_FIELD_MESSAGE);
		expect(html).toContain('Loading fields…');
	});

	it.each([
		[{ rel: '+5d' }, '+d', '5'],
		[{ rel: '-30d' }, '-d', '30'],
		[{ rel: '+2y' }, '+y', '2']
	])('shows the direction of %j', (value, mode, count) => {
		const html = valueInput({ kind: 'field', type: 'film', key: 'released', op: '>=', value });
		expect(html).toMatch(new RegExp(`<option[^>]*value="\\${mode}"[^>]*selected`));
		expect(html).toContain(`value="${count}"`);
		expect(html).toContain('days from now');
	});

	it('names types by their label in a type condition', () => {
		const html = valueInput({ kind: 'type', in: ['film'] });
		expect(html).toMatch(/aria-pressed="true"[^>]*>\s*Film/);
		expect(html).toMatch(/aria-pressed="false"[^>]*>\s*Book/);
		expect(html).not.toMatch(/>\s*film\s*</);
	});

	it('offers "is not one of" for a choice field', () => {
		const html = rowHtml({
			kind: 'field',
			type: 'film',
			key: 'format',
			op: 'not_in',
			value: ['DVD']
		});
		expect(selectedOption(html, 'Condition 1, operator')).toMatch(
			/<option[^>]*selected=""[^>]*>(?:<!---->)?\s*is not one of\s*</
		);
	});

	it('flags an operator the condition cannot use instead of showing another', () => {
		const html = rowHtml({ kind: 'date', on: 'created', op: '!=', value: '2024-01-01' });
		const options = selectedOption(html, 'Condition 1, operator');
		expect(options).toMatch(
			/<option[^>]*selected=""[^>]*>(?:<!---->)?\s*is not on \(not available here\)/
		);
	});

	it('names the compare toggle with the row and shows it as a button', () => {
		const html = valueInput({ kind: 'field', type: 'film', key: 'stock', op: '<=', value: 3 });
		expect(html).toMatch(
			/<button[^>]*data-slot="button"[^>]*aria-label="Condition 1, compare with another field"|<button[^>]*aria-label="Condition 1, compare with another field"[^>]*data-slot="button"/
		);
	});

	it('uses theme colours, not hard-coded amber, for warnings', () => {
		const row = rowHtml({ kind: 'field', type: 'film', key: 'gone', op: '>', value: 3 });
		expect(row).not.toContain('amber');
		const chips = render(QueryChips, {
			props: {
				query: {
					v: 1,
					where: { op: 'and', children: [{ kind: 'favourite', value: true }] },
					sort: []
				},
				lookup: summaryLookup(catalogue),
				warned: new Set(['0']),
				onopen: () => {},
				onremove: () => {},
				onclear: () => {}
			}
		}).body;
		expect(chips).not.toContain('amber');
	});

	it('labels a stale sort from the item types', () => {
		const sorted = (type: string, key: string) =>
			render(QueryBuilder, {
				props: {
					open: true,
					query: { v: 1, where: null, sort: [{ by: 'field', type, key, dir: 'asc' }] },
					catalogue,
					onchange: () => {}
				}
			}).body;
		expect(sorted('film', 'old')).toContain('Film › Old (archived)');
		expect(sorted('zzz', 'k')).toContain('zzz › k (no longer exists)');
	});

	it('shows the depth hint where a group cannot hold another group', () => {
		const deep: Query = {
			v: 1,
			where: {
				op: 'and',
				children: [
					{
						op: 'or',
						children: [
							{
								op: 'and',
								children: [{ op: 'or', children: [{ kind: 'favourite', value: true }] }]
							}
						]
					}
				]
			},
			sort: []
		};
		const html = render(QueryBuilder, {
			props: { open: true, query: deep, catalogue, onchange: () => {} }
		}).body;
		expect(html).toContain('Groups can go 3 levels deep.');
	});
});

describe('date-field chips', () => {
	const lookup = summaryLookup(catalogue);
	const released = (op: string, value: unknown) =>
		describeCondition(
			{ kind: 'field', type: 'film', key: 'released', op, value } as Condition,
			lookup
		);

	it.each([
		['>=', { rel: '-30d' }, 'Film: Released in the last 30 days'],
		['<', { rel: '-30d' }, 'Film: Released more than 30 days ago'],
		['>=', { rel: '+5d' }, 'Film: Released on or after 5 days from now'],
		['<', { rel: '+5d' }, 'Film: Released before 5 days from now'],
		[
			'between',
			[{ rel: '-2w' }, { rel: '+1d' }],
			'Film: Released between 2 weeks ago and 1 day from now'
		]
	])('%s %j', (op, value, expected) => {
		expect(released(op, value)).toBe(expected);
	});

	it('formats an absolute date with date wording', () => {
		expect(released('>=', '2024-03-14')).toBe(
			`Film: Released on or after ${formatIsoDate('2024-03-14', 'short')}`
		);
	});

	it('labels a table column', () => {
		expect(
			describeCondition(
				{ kind: 'field', type: 'film', key: 'cast', sub_key: 'role', op: '=', value: 'Ripley' },
				lookup
			)
		).toBe('Film: Cast › Role is Ripley');
	});
});

describe('BuilderState (the panel actions)', () => {
	const setup = (query: Query = { v: 1, where: null, sort: [] }) => {
		const onchange = vi.fn();
		const state = new BuilderState(query, () => catalogue, onchange);
		return { state, onchange };
	};

	it('adding a condition and filling it in sends the expected tree', () => {
		const { state, onchange } = setup();
		const at = state.addCondition([]);
		expect(at).toEqual([1]);
		expect(onchange).not.toHaveBeenCalled();
		state.update([0], conditionFor(fieldSubject('film', 'stock'), catalogue));
		state.update([0], { kind: 'field', type: 'film', key: 'stock', op: '>=', value: 2 }, true);
		expect(onchange).toHaveBeenLastCalledWith(
			{
				v: 1,
				where: {
					op: 'and',
					children: [{ kind: 'field', type: 'film', key: 'stock', op: '>=', value: 2 }]
				},
				sort: []
			},
			{ debounce: true }
		);
	});

	it('switching the field kind resets the operator and value', () => {
		const start: Query = {
			v: 1,
			where: {
				op: 'and',
				children: [{ kind: 'field', type: 'film', key: 'stock', op: '>', value: 4 }]
			},
			sort: []
		};
		const { state } = setup(start);
		const row = state.shown.where?.children[0] as Condition;
		state.update([0], withSubject(row, fieldSubject('film', 'format'), catalogue));
		expect(state.draft.where?.children[0]).toEqual({
			kind: 'field',
			type: 'film',
			key: 'format',
			op: '='
		});
	});

	it('adds a group holding one row and removes the last row back to no filter', () => {
		const start: Query = {
			v: 1,
			where: { op: 'and', children: [{ kind: 'favourite', value: true }] },
			sort: []
		};
		const { state, onchange } = setup(start);
		expect(state.addGroup([])).toEqual([1, 0]);
		state.remove([1]);
		expect(state.remove([0])).toBe(1);
		expect(onchange).toHaveBeenLastCalledWith({ v: 1, where: null, sort: [] }, { debounce: false });
	});

	it('follows the URL only when it changed from elsewhere', () => {
		const { state } = setup();
		state.addCondition([]);
		state.sync({ v: 1, where: null, sort: [] });
		// The shown blank row plus the added one; the unchanged URL leaves them alone.
		expect(state.draft.where?.children).toHaveLength(2);
		state.sync({
			v: 1,
			where: { op: 'and', children: [{ kind: 'favourite', value: false }] },
			sort: []
		});
		expect(state.draft.where?.children).toEqual([{ kind: 'favourite', value: false }]);
	});
});

describe('per-item fields', () => {
	const itemFields = [
		{ key: 'signed', kind: 'boolean', label: 'Signed', count: 2 },
		{ key: 'mood', kind: 'choice', label: 'Mood', count: 1 },
		{ key: 'tags', kind: 'multichoice', label: 'Moods', count: 1 }
	];
	const withFields = buildCatalogue(itemTypes, true, itemFields);
	const row = (condition: Condition, cat = withFields) =>
		render(QueryConditionRow, {
			props: {
				condition,
				path: [0],
				view: stubView({ catalogue: cat, numbers: new Map([['0', 1]]) })
			}
		}).body;
	const perItem = (key: string, kind: string, op: string, value?: unknown): Condition =>
		({
			kind: 'field',
			field_kind: kind,
			key,
			op,
			...(value === undefined ? {} : { value })
		}) as Condition;

	it('shows the chosen per-item field under its group on the trigger', () => {
		const html = row(perItem('signed', 'boolean', '='));
		expect(html).toContain('aria-label="Condition 1, field"');
		expect(html).toContain('Per-item fields › Signed');
		expect(html).toContain('aria-label="Condition 1, operator"');
		expect(html).not.toContain(NO_ITEM_FIELD_MESSAGE);
	});

	it('flags a per-item field no item has, with its own wording', () => {
		const html = row(perItem('gone', 'number', '>', 3));
		expect(html).toContain(NO_ITEM_FIELD_MESSAGE);
		expect(html).not.toContain(STALE_FIELD_MESSAGE);
		expect(html).toContain('Per-item fields › gone (no item has this field)');
	});

	it('does not flag a per-item field when the listing was not read', () => {
		const html = row(perItem('signed', 'boolean', '='), buildCatalogue(itemTypes, true, null));
		expect(html).not.toContain(NO_ITEM_FIELD_MESSAGE);
	});

	it('uses typed text for a per-item choice, which has no option list', () => {
		const single = valueInput2(perItem('mood', 'choice', '=', 'calm'));
		expect(single).toContain('aria-label="Condition 1, value"');
		expect(single).toContain('value="calm"');
		expect(single).not.toContain('has no options');
		const many = valueInput2(perItem('mood', 'choice', 'in', ['calm', 'tense']));
		expect(many).toContain('Separate values with commas');
		expect(many).not.toContain('has no options');
		const has = valueInput2(perItem('tags', 'multichoice', 'has', ['calm']));
		expect(has).toContain('Separate values with commas');
		expect(has).not.toContain('has no options');
	});

	it('reads a per-item boolean as yes or no', () => {
		const html = valueInput2(perItem('signed', 'boolean', '=', true));
		expect(html).toContain('aria-pressed="true"');
	});

	it('words the chip and warns about a missing field', () => {
		const query: Query = {
			v: 1,
			where: {
				op: 'and',
				children: [perItem('signed', 'boolean', '=', true), perItem('gone', 'number', '>', 3)]
			},
			sort: []
		};
		const html = render(QueryChips, {
			props: {
				query,
				lookup: summaryLookup(withFields),
				catalogue: withFields,
				onopen: () => {},
				onremove: () => {},
				onclear: () => {}
			}
		}).body;
		expect(html).toContain('Per-item field › Signed: is yes');
		expect(html).toContain(NO_ITEM_FIELD_MESSAGE);
		expect(html).not.toContain(STALE_FIELD_MESSAGE);
	});

	it('lists the paths of per-item rows whose field is missing', () => {
		const query: Query = {
			v: 1,
			where: {
				op: 'and',
				children: [
					perItem('signed', 'boolean', '=', true),
					{ op: 'or', children: [perItem('gone', 'number', '>', 3)] },
					{ kind: 'field', type: 'film', key: 'gone', op: '=', value: 1 }
				]
			},
			sort: []
		};
		expect([...missingItemFieldPaths(query, withFields)]).toEqual(['1.0']);
		expect(missingItemFieldPaths(query, buildCatalogue(itemTypes, true, null)).size).toBe(0);
	});

	it('offers the per-item options under their group, found by group name or label', () => {
		const items = itemFieldPickerItems(withFields);
		expect(items.map((i) => i.value)).toEqual([
			'item:boolean:signed',
			'item:choice:mood',
			'item:multichoice:tags'
		]);
		expect(items[0]).toMatchObject({
			label: 'Signed',
			group: 'Per-item fields',
			selectedLabel: 'Per-item fields › Signed'
		});
		expect(filterComboboxItems(items, 'per-item').length).toBe(3);
		expect(filterComboboxItems(items, 'signed').length).toBe(1);
		expect(itemFieldPickerItems(catalogue)).toEqual([]);
	});
});
