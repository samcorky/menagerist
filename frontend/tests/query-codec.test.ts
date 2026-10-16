import { describe, expect, it } from 'vitest';
import { decodeQuery, encodeQuery } from '$lib/query/codec';
import type { Query } from '$lib/query/types';

const query: Query = {
	v: 1,
	where: {
		op: 'and',
		children: [
			{ kind: 'field', type: 'film', key: 'title', op: '~', value: 'café ✓ 🎬' },
			{ op: 'or', children: [{ kind: 'favourite', value: true }] }
		]
	},
	sort: [{ by: 'name', dir: 'asc' }]
};

const b64 = (text: string) => Buffer.from(text, 'utf-8').toString('base64url');
const token = (value: unknown) => b64(JSON.stringify(value));
const fav = { kind: 'favourite', value: true };
const group = (op: string, children: unknown[]) => ({ op, children });
const wrap = (where: unknown, sort: unknown = []) => token({ v: 1, where, sort });

describe('encodeQuery', () => {
	it('produces unpadded base64url', () => {
		// Text chosen so standard base64 would contain +, / and =.
		const awkward: Query = {
			v: 1,
			where: { op: 'and', children: [{ kind: 'text', q: '???>>>~~~' }] },
			sort: []
		};
		for (const q of [query, awkward]) expect(encodeQuery(q)).toMatch(/^[A-Za-z0-9_-]+$/);
	});
});

describe('decodeQuery', () => {
	it('round-trips, including non-ASCII text', () => {
		expect(decodeQuery(encodeQuery(query))).toEqual(query);
	});

	it('round-trips an empty query', () => {
		const empty: Query = { v: 1, where: null, sort: [] };
		expect(decodeQuery(encodeQuery(empty))).toEqual(empty);
	});

	it('round-trips every condition kind and operand shape', () => {
		const full: Query = {
			v: 1,
			where: {
				op: 'and',
				children: [
					{ kind: 'text', q: 'alien' },
					{ kind: 'type', in: ['film', 'book'] },
					{ kind: 'favourite', value: false },
					{ kind: 'tag', mode: 'any', tags: ['a', 'b'] },
					{ kind: 'date', on: 'created', op: '>=', value: { rel: '-30d' } },
					{ kind: 'field', type: 'film', key: 'budget', op: 'between', value: [1, 2] },
					{
						kind: 'field',
						type: 'film',
						key: 'cost',
						op: '>',
						value: { value: 5, currency: 'GBP' }
					},
					{ kind: 'field', type: 'film', key: 'a', op: '=', value: { ref: 'b' } },
					{ kind: 'field', type: 'film', key: 'rows', sub_key: 'col', op: 'empty' },
					{ op: 'not', children: [{ kind: 'field', type: 'film', key: 'x', op: '=', value: true }] }
				]
			},
			sort: [
				{ by: 'created', dir: 'desc' },
				{ by: 'field', dir: 'asc', type: 'film', key: 'title' }
			]
		};
		expect(decodeQuery(encodeQuery(full))).toEqual(full);
	});

	it.each([
		['empty', ''],
		['bad base64', '!!!'],
		['not JSON', b64('hello')],
		['empty object', 'e30'],
		['bad UTF-8', Buffer.from([0xff, 0xfe, 0xfd]).toString('base64url')],
		['standard base64 with padding chars', btoa('{"v":2,"where":null,"sort":[]}')],
		['JSON null', b64('null')],
		['JSON array', b64('[]')],
		['JSON string', b64('"x"')]
	])('rejects %s', (_name, input) => {
		expect(decodeQuery(input)).toBeNull();
	});

	it('accepts not_in with a list like in, and rejects a scalar', () => {
		const q = (value: unknown) =>
			token({
				v: 1,
				where: {
					op: 'and',
					children: [{ kind: 'field', type: 't', key: 'k', op: 'not_in', value }]
				},
				sort: []
			});
		expect(decodeQuery(q(['a', 'b']))?.where?.children[0]).toEqual({
			kind: 'field',
			type: 't',
			key: 'k',
			op: 'not_in',
			value: ['a', 'b']
		});
		expect(decodeQuery(q('a'))).toBeNull();
		expect(decodeQuery(q([]))).toBeNull();
		expect(decodeQuery(q(Array.from({ length: 51 }, (_, i) => `v${i}`)))).toBeNull();
	});

	it('rejects the wrong version', () => {
		expect(decodeQuery(token({ v: 2, where: null, sort: [] }))).toBeNull();
		expect(decodeQuery(token({ where: null, sort: [] }))).toBeNull();
	});

	it('accepts a missing where or sort, as the server does', () => {
		const empty: Query = { v: 1, where: null, sort: [] };
		expect(decodeQuery(token({ v: 1, sort: [] }))).toEqual(empty);
		expect(decodeQuery(token({ v: 1, where: null }))).toEqual(empty);
		expect(decodeQuery(token({ v: 1 }))).toEqual(empty);
	});

	it('rejects a malformed where or sort', () => {
		expect(decodeQuery(token({ v: 1, where: 'x', sort: [] }))).toBeNull();
		expect(decodeQuery(token({ v: 1, where: fav, sort: [] }))).toBeNull();
		expect(decodeQuery(token({ v: 1, where: null, sort: {} }))).toBeNull();
		expect(decodeQuery(token({ v: 1, where: null, sort: null }))).toBeNull();
	});

	it('rejects bad sort keys and too many of them', () => {
		const key = { by: 'name' };
		expect(decodeQuery(wrap(null, [key, key, key]))).not.toBeNull();
		expect(decodeQuery(wrap(null, [key, key, key, key]))).toBeNull();
		expect(decodeQuery(wrap(null, [{ by: 'size' }]))).toBeNull();
		expect(decodeQuery(wrap(null, [{ by: 'name', dir: 'up' }]))).toBeNull();
		expect(decodeQuery(wrap(null, ['name']))).toBeNull();
		expect(decodeQuery(wrap(null, [{ by: 'field' }]))).toBeNull();
		expect(decodeQuery(wrap(null, [{ by: 'field', type: 1, key: 'k' }]))).toBeNull();
	});

	it('rejects an unknown or non-string kind', () => {
		expect(decodeQuery(wrap(group('and', [{ kind: 'colour' }])))).toBeNull();
		expect(decodeQuery(wrap(group('and', [{ kind: 5 }])))).toBeNull();
	});

	it('rejects non-object children', () => {
		expect(decodeQuery(wrap(group('and', ['x'])))).toBeNull();
		expect(decodeQuery(wrap(group('and', [null])))).toBeNull();
		expect(decodeQuery(wrap(group('and', [[]])))).toBeNull();
	});

	it.each([
		['text q', { kind: 'text', q: 5 }],
		['text missing q', { kind: 'text' }],
		['type in', { kind: 'type', in: 'film' }],
		['type in items', { kind: 'type', in: [1] }],
		['favourite value', { kind: 'favourite', value: 'yes' }],
		['tag mode', { kind: 'tag', mode: 'some', tags: ['a'] }],
		['tag tags', { kind: 'tag', mode: 'any', tags: [1] }],
		['date on', { kind: 'date', on: 'deleted', op: '=', value: '2020-01-01' }],
		['date op', { kind: 'date', on: 'created', op: 5, value: '2020-01-01' }],
		['date value', { kind: 'date', on: 'created', op: '=' }],
		['field type', { kind: 'field', type: 1, key: 'k', op: '=', value: 1 }],
		['field key', { kind: 'field', type: 't', op: '=', value: 1 }],
		['field op', { kind: 'field', type: 't', key: 'k', op: ['='], value: 1 }],
		['field sub_key', { kind: 'field', type: 't', key: 'k', sub_key: 3, op: '=', value: 1 }],
		['field value null', { kind: 'field', type: 't', key: 'k', op: '=', value: null }],
		['field value object', { kind: 'field', type: 't', key: 'k', op: '=', value: { x: 1 } }],
		['field value rel', { kind: 'field', type: 't', key: 'k', op: '=', value: { rel: 3 } }],
		[
			'field value money',
			{ kind: 'field', type: 't', key: 'k', op: '=', value: { value: '1', currency: 'GBP' } }
		],
		['field value nested list', { kind: 'field', type: 't', key: 'k', op: 'in', value: [[1]] }]
	])('rejects wrong field types: %s', (_name, condition) => {
		expect(decodeQuery(wrap(group('and', [condition])))).toBeNull();
	});

	it('rejects empty groups and a not with other than one child', () => {
		expect(decodeQuery(wrap(group('and', [])))).toBeNull();
		expect(decodeQuery(wrap(group('or', [fav, group('and', [])])))).toBeNull();
		expect(decodeQuery(wrap({ op: 'and' }))).toBeNull();
		expect(decodeQuery(wrap({ op: 'and', children: 'x' }))).toBeNull();
		expect(decodeQuery(wrap(group('not', [])))).toBeNull();
		expect(decodeQuery(wrap(group('not', [fav, fav])))).toBeNull();
		expect(decodeQuery(wrap(group('not', [fav])))).not.toBeNull();
		expect(decodeQuery(wrap(group('xor', [fav])))).toBeNull();
	});

	it('limits nesting to four groups', () => {
		const nest = (levels: number): unknown =>
			levels === 1 ? group('and', [fav]) : group('and', [fav, nest(levels - 1)]);
		expect(decodeQuery(wrap(nest(4)))).not.toBeNull();
		expect(decodeQuery(wrap(nest(5)))).toBeNull();
	});

	it('does not overflow the stack on enormous nesting', () => {
		const depth = 10_000;
		const json =
			'{"op":"and","children":['.repeat(depth) +
			'{"kind":"favourite","value":true}' +
			']}'.repeat(depth);
		const input = b64(`{"v":1,"where":${json},"sort":[]}`);
		expect(() => decodeQuery(input)).not.toThrow();
		expect(decodeQuery(input)).toBeNull();
	});

	it('limits the total number of conditions to 50', () => {
		const many = (n: number) => Array.from({ length: n }, () => fav);
		expect(decodeQuery(wrap(group('and', many(50))))).not.toBeNull();
		expect(decodeQuery(wrap(group('and', many(51))))).toBeNull();
		expect(
			decodeQuery(wrap(group('and', [group('or', many(30)), group('or', many(21))])))
		).toBeNull();
	});

	it('limits strings to 200 characters and lists to 50 items', () => {
		const text = (q: string) => wrap(group('and', [{ kind: 'text', q }]));
		expect(decodeQuery(text('a'.repeat(200)))).not.toBeNull();
		expect(decodeQuery(text('a'.repeat(201)))).toBeNull();
		const field = (value: unknown) =>
			wrap(group('and', [{ kind: 'field', type: 't', key: 'k', op: '=', value }]));
		expect(decodeQuery(field('a'.repeat(201)))).toBeNull();
		const types = (n: number) =>
			wrap(group('and', [{ kind: 'type', in: Array.from({ length: n }, () => 't') }]));
		expect(decodeQuery(types(50))).not.toBeNull();
		expect(decodeQuery(types(51))).toBeNull();
	});

	it('drops a null sub_key, as the server treats it as none', () => {
		const field = { kind: 'field', type: 't', key: 'k', op: 'empty' };
		const decoded = decodeQuery(wrap(group('and', [{ ...field, sub_key: null }])));
		expect(decoded).toEqual({ v: 1, where: group('and', [field]), sort: [] });
	});

	it('drops unknown properties from the result', () => {
		const decoded = decodeQuery(
			token({ v: 1, extra: 1, where: group('and', [{ ...fav, junk: 1 }]), sort: [] })
		);
		expect(decoded).toEqual({ v: 1, where: group('and', [fav]), sort: [] });
	});

	describe('non-finite numbers', () => {
		// JSON.stringify cannot write Infinity, so these tokens are built from raw JSON text.
		const raw = (where: string) => b64(`{"v":1,"where":${where},"sort":[]}`);
		const cond = (value: string, op = '=') =>
			raw(
				`{"op":"and","children":[{"kind":"field","type":"t","key":"k","op":"${op}","value":${value}}]}`
			);

		it.each([
			['a plain operand', cond('1e999')],
			['a negative operand', cond('-1e999')],
			['a between bound', cond('[1, 1e999]', 'between')],
			['an in member', cond('[1e999]', 'in')],
			['a not_in member', cond('[1e999]', 'not_in')],
			['a money amount', cond('{"value": 1e999, "currency": "GBP"}')]
		])('rejects %s that overflows to infinity', (_, t) => {
			expect(() => decodeQuery(t)).not.toThrow();
			expect(decodeQuery(t)).toBeNull();
		});

		it('still accepts large finite numbers', () => {
			expect(decodeQuery(cond('1e308'))).not.toBeNull();
			expect(decodeQuery(cond('{"value": 1e308, "currency": "GBP"}'))).not.toBeNull();
		});
	});
});
