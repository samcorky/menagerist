import { describe, expect, it } from 'vitest';
import { describeCondition } from '$lib/query/summary';
import { OPERATOR_LABELS } from '$lib/query/operators';
import type { Condition } from '$lib/query/types';

const lookup = {
	typeLabel: (slug: string) => (slug === 'film' ? 'Film' : slug === 'album' ? 'Album' : slug),
	fieldLabel: (_type: string, key: string) => (key === 'rating' ? 'Rating' : key)
};

const field = (op: string, value?: unknown): Condition =>
	({ kind: 'field', type: 'film', key: 'rating', op, value }) as Condition;
const date = (op: string, value: unknown, on: 'created' | 'updated' = 'created'): Condition =>
	({ kind: 'date', on, op, value }) as Condition;

describe('describeCondition', () => {
	it.each([
		[
			{ kind: 'field', type: 'film', key: 'rating', op: '>=', value: 4 },
			'Film: Rating is at least 4'
		],
		[
			{ kind: 'field', type: 'film', key: 'rating', op: 'between', value: [3, 5] },
			'Film: Rating is between 3 and 5'
		],
		[{ kind: 'field', type: 'film', key: 'rating', op: 'empty' }, 'Film: Rating is empty'],
		[
			{ kind: 'field', type: 'film', key: 'stock', op: '<=', value: { ref: 'reorder_at' } },
			'Film: stock is at most reorder_at'
		],
		[{ kind: 'tag', mode: 'any', tags: ['noir', 'classic'] }, 'Tag is any of noir, classic'],
		[{ kind: 'favourite', value: true }, 'Is a favourite'],
		[{ kind: 'text', q: 'alien' }, 'Contains “alien”'],
		[{ kind: 'date', on: 'created', op: '>=', value: { rel: '-30d' } }, 'Added in the last 30 days']
	] as const)('%j', (condition, expected) => {
		expect(describeCondition(condition as Condition, lookup)).toBe(expected);
	});

	it('words every operator', () => {
		for (const [op, label] of Object.entries(OPERATOR_LABELS)) {
			const text = describeCondition(field(op, op === 'between' ? [1, 2] : 3), lookup);
			expect(text.startsWith(`Film: Rating ${label}`)).toBe(true);
		}
	});

	it('omits the value for operators without one', () => {
		expect(describeCondition(field('not_empty', 5), lookup)).toBe('Film: Rating is not empty');
		expect(describeCondition(field('incomplete'), lookup)).toBe('Film: Rating has unticked items');
	});

	it('lists values for in and has', () => {
		expect(describeCondition(field('in', ['a', 'b', 'c']), lookup)).toBe(
			'Film: Rating is one of a, b, c'
		);
		expect(describeCondition(field('has', ['x']), lookup)).toBe('Film: Rating includes x');
	});

	it('lists values for not_in', () => {
		expect(describeCondition(field('not_in', ['Horror', 'Comedy']), lookup)).toBe(
			'Film: Rating is not one of Horror, Comedy'
		);
	});

	it('words booleans and money', () => {
		expect(describeCondition(field('=', true), lookup)).toBe('Film: Rating is yes');
		expect(describeCondition(field('=', false), lookup)).toBe('Film: Rating is no');
		expect(describeCondition(field('>', { value: 12.5, currency: 'GBP' }), lookup)).toBe(
			'Film: Rating is more than 12.50 GBP'
		);
		expect(
			describeCondition(
				field('between', [
					{ value: 1, currency: 'EUR' },
					{ value: 2, currency: 'EUR' }
				]),
				lookup
			)
		).toBe('Film: Rating is between 1.00 EUR and 2.00 EUR');
	});

	it('includes a sub key', () => {
		const c: Condition = {
			kind: 'field',
			type: 'film',
			key: 'rating',
			sub_key: 'avg',
			op: '=',
			value: 2
		};
		expect(describeCondition(c, lookup)).toBe('Film: Rating › avg is 2');
	});

	it('falls back to raw slugs and keys', () => {
		const c: Condition = { kind: 'field', type: 'zine', key: 'pages', op: '>', value: 10 };
		expect(describeCondition(c, lookup)).toBe('zine: pages is more than 10');
	});

	it('words type conditions', () => {
		expect(describeCondition({ kind: 'type', in: ['film'] }, lookup)).toBe('Type is Film');
		expect(describeCondition({ kind: 'type', in: ['film', 'album'] }, lookup)).toBe(
			'Type is Film or Album'
		);
		expect(describeCondition({ kind: 'type', in: ['a', 'film', 'album'] }, lookup)).toBe(
			'Type is a, Film or Album'
		);
	});

	it('words tag modes and favourites', () => {
		expect(describeCondition({ kind: 'tag', mode: 'all', tags: ['a', 'b'] }, lookup)).toBe(
			'Tag is all of a, b'
		);
		expect(describeCondition({ kind: 'tag', mode: 'none', tags: ['a'] }, lookup)).toBe(
			'Tag is none of a'
		);
		expect(describeCondition({ kind: 'favourite', value: false }, lookup)).toBe(
			'Is not a favourite'
		);
	});

	describe('formatValue hook', () => {
		const calls: unknown[][] = [];
		const hooked = (fn: (v: unknown) => string | null | undefined) => ({
			...lookup,
			formatValue: (t: string, k: string, sk: string | undefined, v: unknown) => {
				calls.push([t, k, sk, v]);
				return fn(v) as string | null;
			}
		});
		const mins = (v: unknown) => (typeof v === 'number' ? `${v / 60} min` : null);

		it('formats single, between and list values', () => {
			expect(describeCondition(field('<=', 2700), hooked(mins))).toBe(
				'Film: Rating is at most 45 min'
			);
			expect(describeCondition(field('between', [60, 120]), hooked(mins))).toBe(
				'Film: Rating is between 1 min and 2 min'
			);
			expect(describeCondition(field('in', [60, 120]), hooked(mins))).toBe(
				'Film: Rating is one of 1 min, 2 min'
			);
			expect(describeCondition(field('has', [60]), hooked(mins))).toBe(
				'Film: Rating includes 1 min'
			);
		});
		it('passes the field identity', () => {
			calls.length = 0;
			const c: Condition = {
				kind: 'field',
				type: 'film',
				key: 'rating',
				sub_key: 'avg',
				op: '=',
				value: 60
			};
			describeCondition(c, hooked(mins));
			expect(calls).toEqual([['film', 'rating', 'avg', 60]]);
		});
		it('works without a hook', () => {
			expect(describeCondition(field('<=', 2700), lookup)).toBe('Film: Rating is at most 2700');
		});
		it('falls back when the hook returns null or undefined', () => {
			expect(describeCondition(field('=', 'x'), hooked(mins))).toBe('Film: Rating is x');
			expect(
				describeCondition(
					field('=', 'x'),
					hooked(() => undefined)
				)
			).toBe('Film: Rating is x');
		});
		it('falls back when the hook throws', () => {
			const boom = {
				...lookup,
				formatValue: () => {
					throw new Error('x');
				}
			};
			expect(describeCondition(field('>', 5), boom)).toBe('Film: Rating is more than 5');
		});
		it('is not called for refs, offsets or other conditions', () => {
			calls.length = 0;
			const l = hooked(() => 'X');
			describeCondition(field('<=', { ref: 'other' }), l);
			describeCondition(field('>=', { rel: '-3d' }), l);
			describeCondition(date('>=', 5), l);
			describeCondition({ kind: 'text', q: 'a' }, l);
			describeCondition({ kind: 'tag', mode: 'any', tags: ['a'] }, l);
			describeCondition({ kind: 'type', in: ['film'] }, l);
			describeCondition({ kind: 'favourite', value: true }, l);
			expect(calls).toEqual([]);
		});
		it('formats money without a hook', () => {
			expect(describeCondition(field('=', { value: 3.5, currency: 'GBP' }), lookup)).toBe(
				'Film: Rating is 3.50 GBP'
			);
		});
	});

	describe('dates', () => {
		it('uses Added and Changed', () => {
			expect(describeCondition(date('>=', { rel: '-1w' }, 'updated'), lookup)).toBe(
				'Changed in the last week'
			);
		});
		it('words absolute values', () => {
			expect(describeCondition(date('=', '2024-05-01'), lookup)).toBe('Added on 2024-05-01');
			expect(describeCondition(date('>', '2024-05-01'), lookup)).toBe('Added after 2024-05-01');
			expect(describeCondition(date('>=', '2024-05-01'), lookup)).toBe(
				'Added on or after 2024-05-01'
			);
			expect(describeCondition(date('<', '2024-05-01'), lookup)).toBe('Added before 2024-05-01');
			expect(describeCondition(date('<=', '2024-05-01'), lookup)).toBe(
				'Added on or before 2024-05-01'
			);
			expect(describeCondition(date('between', ['2024-01-01', '2024-02-01']), lookup)).toBe(
				'Added between 2024-01-01 and 2024-02-01'
			);
		});
		it('words negative offsets with singular and plural units', () => {
			expect(describeCondition(date('>=', { rel: '-1d' }), lookup)).toBe('Added in the last day');
			expect(describeCondition(date('>', { rel: '-2w' }), lookup)).toBe(
				'Added in the last 2 weeks'
			);
			expect(describeCondition(date('>=', { rel: '-6m' }), lookup)).toBe(
				'Added in the last 6 months'
			);
			expect(describeCondition(date('>=', { rel: '-1y' }), lookup)).toBe('Added in the last year');
			expect(describeCondition(date('<', { rel: '-3y' }), lookup)).toBe(
				'Added more than 3 years ago'
			);
			expect(describeCondition(date('=', { rel: '-1m' }), lookup)).toBe('Added 1 month ago');
		});
		it('words positive offsets', () => {
			expect(describeCondition(date('<', { rel: '+2w' }, 'updated'), lookup)).toBe(
				'Changed before 2 weeks from now'
			);
			expect(describeCondition(date('>=', { rel: '1d' }), lookup)).toBe(
				'Added on or after 1 day from now'
			);
			expect(describeCondition(date('=', { rel: '3m' }), lookup)).toBe('Added 3 months from now');
		});
		it('words between with relative ends', () => {
			expect(describeCondition(date('between', [{ rel: '-2w' }, { rel: '+1d' }]), lookup)).toBe(
				'Added between 2 weeks ago and 1 day from now'
			);
		});
	});

	describe('malformed input', () => {
		it('never throws', () => {
			const bad = [
				field('between', 5),
				field('between', [1]),
				field('in', 'x'),
				field('>='),
				field('weird', 1),
				field('=', { odd: true }),
				field('=', null),
				date('>=', { rel: 'soon' }),
				date('>=', { rel: 5 }),
				date('between', 'x'),
				date('~', undefined),
				{ kind: 'tag', mode: 'any' },
				{ kind: 'type' },
				{ kind: 'text' },
				{ kind: 'nope' },
				{ kind: 'field' },
				null,
				undefined,
				42
			];
			for (const c of bad) {
				const text = describeCondition(c as unknown as Condition, lookup);
				expect(typeof text).toBe('string');
				expect(text.length).toBeGreaterThan(0);
			}
		});
		it('keeps unparsable relative values as written', () => {
			expect(describeCondition(date('>=', { rel: 'soon' }), lookup)).toBe('Added on or after soon');
		});
		it('survives a throwing lookup', () => {
			const boom = {
				typeLabel: () => {
					throw new Error('x');
				},
				fieldLabel: () => 'y'
			};
			expect(typeof describeCondition(field('='), boom)).toBe('string');
		});
	});
});
