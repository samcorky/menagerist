import { describe, expect, it } from 'vitest';
import contract from '$shared/contracts/query-shapes.json';
import { decodeQuery, encodeQuery } from '$lib/query/codec';
import type { Query } from '$lib/query/types';

// The backend parser is held to the same file (test_query_shapes_contract.py), so a
// link the browser decodes is one the server accepts. The server's error paths are
// ignored here: the decoder only says whether a query is well formed.
const decode = (query: unknown) => decodeQuery(encodeQuery(query as Query));

type Shape = { name: string; query: unknown };

describe('query shapes contract', () => {
	it('has cases', () => {
		expect(contract.valid.length).toBeGreaterThan(50);
		expect(contract.invalid.length).toBeGreaterThan(100);
	});

	it('names every case once', () => {
		for (const section of [contract.valid, contract.invalid]) {
			const names = section.map((c: Shape) => c.name);
			expect(new Set(names).size).toBe(names.length);
		}
	});

	it.each(contract.valid.map((c: Shape) => [c.name, c.query] as const))(
		'accepts valid: %s',
		(_name, query) => {
			expect(decode(query)).not.toBeNull();
		}
	);

	it.each(contract.invalid.map((c: Shape) => [c.name, c.query] as const))(
		'rejects invalid: %s',
		(_name, query) => {
			expect(decode(query)).toBeNull();
		}
	);
});

// Bulk cases are generated here rather than stored in the fixture; the backend test
// generates the same ones. Each is [name, query, valid].
const fav = { kind: 'favourite', value: true };
const where = (...children: unknown[]) => ({
	v: 1,
	where: { op: 'and', children },
	sort: []
});
const field = (op: string, extra: Record<string, unknown>) => ({
	kind: 'field',
	type: 'film',
	key: 'year',
	op,
	...extra
});

function bulk(): [string, unknown, boolean][] {
	const cases: [string, unknown, boolean][] = [];
	for (const size of [200, 201]) {
		const ok = size === 200;
		const text = 'a'.repeat(size);
		cases.push([`text of ${size}`, where({ kind: 'text', q: text }), ok]);
		cases.push([`type slug of ${size}`, where({ kind: 'type', in: [text] }), ok]);
		cases.push([
			`description of ${size}`,
			where({ kind: 'description', op: '~', value: text }),
			ok
		]);
		cases.push([`name of ${size}`, where({ kind: 'name', op: '=', value: text }), ok]);
		cases.push([`tag of ${size}`, where({ kind: 'tag', mode: 'any', tags: [text] }), ok]);
		cases.push([`field type of ${size}`, where(field('=', { type: text, value: 1 })), ok]);
		cases.push([`field key of ${size}`, where(field('=', { key: text, value: 1 })), ok]);
		cases.push([`sub_key of ${size}`, where(field('=', { sub_key: text, value: 1 })), ok]);
		cases.push([`string operand of ${size}`, where(field('=', { value: text })), ok]);
		cases.push([`reference of ${size}`, where(field('=', { value: { ref: text } })), ok]);
		const money = { value: 1, currency: text };
		cases.push([`currency of ${size}`, where(field('=', { value: money })), ok]);
		const sort = [{ by: 'field', type: text, key: 'k' }];
		cases.push([`sort type of ${size}`, { v: 1, where: null, sort }, ok]);
		const sortKey = [{ by: 'field', type: 't', key: text }];
		cases.push([`sort key of ${size}`, { v: 1, where: null, sort: sortKey }, ok]);
		cases.push([`in item of ${size}`, where(field('in', { value: ['a', text] })), ok]);
		cases.push([`between item of ${size}`, where(field('between', { value: ['a', text] })), ok]);
		const astral = '🎬'.repeat(size);
		cases.push([
			`tag of ${size} astral characters`,
			where({ kind: 'tag', mode: 'any', tags: [astral] }),
			ok
		]);
		cases.push([
			`field key of ${size} astral characters`,
			where(field('=', { key: astral, value: 1 })),
			ok
		]);
		cases.push([
			`string operand of ${size} astral characters`,
			where(field('=', { value: astral })),
			ok
		]);
	}
	for (const size of [50, 51]) {
		const ok = size === 50;
		const items = Array.from({ length: size }, () => 'a');
		cases.push([`type list of ${size}`, where({ kind: 'type', in: items }), ok]);
		cases.push([`tag list of ${size}`, where({ kind: 'tag', mode: 'any', tags: items }), ok]);
		cases.push([`in list of ${size}`, where(field('in', { value: items })), ok]);
		cases.push([`has list of ${size}`, where(field('has', { value: items })), ok]);
		const ids = Array.from(
			{ length: size },
			(_, n) => `00000000-0000-0000-0000-${String(n).padStart(12, '0')}`
		);
		cases.push([
			`collection list of ${size}`,
			where({ kind: 'collection', mode: 'any', in: ids }),
			ok
		]);
	}
	// Length counts characters, not UTF-16 units.
	cases.push(['text of 200 astral characters', where({ kind: 'text', q: '🎬'.repeat(200) }), true]);
	cases.push([
		'text of 201 astral characters',
		where({ kind: 'text', q: '🎬'.repeat(201) }),
		false
	]);
	for (const count of [50, 51]) {
		cases.push([
			`${count} conditions`,
			where(...Array.from({ length: count }, () => fav)),
			count === 50
		]);
	}
	const many = (n: number) => Array.from({ length: n }, () => fav);
	cases.push([
		'50 conditions across groups',
		where({ op: 'or', children: many(30) }, { op: 'or', children: many(20) }),
		true
	]);
	cases.push([
		'conditions counted across groups',
		where({ op: 'or', children: many(30) }, { op: 'or', children: many(21) }),
		false
	]);
	return cases;
}

describe('query shapes contract: generated boundaries', () => {
	it.each(bulk())('%s', (_name, query, valid) => {
		if (valid) expect(decode(query)).not.toBeNull();
		else expect(decode(query)).toBeNull();
	});
});
