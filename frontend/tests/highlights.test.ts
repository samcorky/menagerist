import { readFileSync } from 'node:fs';
import { describe, it, expect } from 'vitest';
import '../src/lib/field-types/index';
import {
	MAX_CONNECTION_HIGHLIGHTS,
	MAX_HIGHLIGHTS,
	SURFACE_LIMITS,
	canHighlightMore,
	highlightRanks,
	isHighlightable,
	maxHighlights,
	movedRanks,
	normaliseHighlights,
	summaryItems,
	toggledRanks
} from '../src/lib/highlights';
import { readHighlights, readSchemaMeta, withHighlights } from '../src/lib/schema-meta';
import { itemsToSchema, schemaToItems } from '../src/lib/components/schema-editor.svelte';
import { archiveField } from '../src/lib/field-archive';
import type { AttributesSchema, EditorField, JsonSchemaProperty } from '../src/lib/schema-types';

function field(key: string, kind: string, extra: Partial<EditorField> = {}): EditorField {
	return { key, label: key, kind, required: false, options: [], subFields: [], ...extra };
}

const props = {
	director: { title: 'Director', type: 'string', 'x-menagerist': { kind: 'text' } },
	year: { title: 'Year', type: 'number' },
	seen: { title: 'Seen', type: 'boolean' },
	released: { title: 'Released', type: 'string', format: 'date' },
	genre: { title: 'Genre', type: 'string', enum: ['Sci-fi', 'Drama'] },
	stars: {
		title: 'My rating',
		type: 'number',
		minimum: 1,
		maximum: 5,
		multipleOf: 1,
		'x-menagerist': { kind: 'rating' }
	},
	notes: { title: 'Notes', type: 'string', 'x-menagerist': { kind: 'longtext' } },
	cast: {
		title: 'Cast',
		type: 'array',
		items: { type: 'object', properties: { name: { title: 'Name', type: 'string' } } }
	},
	old: { title: 'Old', type: 'string', 'x-menagerist': { kind: 'text', archived: true } }
} as unknown as Record<string, JsonSchemaProperty>;

function schemaWith(card: { key: string }[]): AttributesSchema {
	return {
		$schema: 'https://json-schema.org/draft/2020-12/schema',
		type: 'object',
		properties: props,
		'x-menagerist': { version: 1, highlights: { card } }
	} as AttributesSchema;
}

describe('isHighlightable', () => {
	it('is true for scalar kinds and false for long text, tables and unknown shapes', () => {
		for (const key of ['director', 'year', 'seen', 'released', 'genre', 'stars']) {
			expect(isHighlightable(props[key]), key).toBe(true);
		}
		for (const key of ['notes', 'cast']) expect(isHighlightable(props[key]), key).toBe(false);
		expect(isHighlightable({ title: 'x', type: 'string', 'x-menagerist': { kind: 'zzz' } })).toBe(
			false
		);
		expect(isHighlightable(undefined)).toBe(false);
	});
});

describe('normaliseHighlights', () => {
	it('keeps valid keys in order', () => {
		expect(normaliseHighlights([{ key: 'stars' }, { key: 'director' }], props)).toEqual([
			{ key: 'stars' },
			{ key: 'director' }
		]);
	});

	it('drops dangling, archived, non-highlightable and duplicate keys', () => {
		const list = [
			{ key: 'missing' },
			{ key: 'old' },
			{ key: 'notes' },
			{ key: 'cast' },
			{ key: 'director' },
			{ key: 'director' },
			{ key: 'constructor' }
		];
		expect(normaliseHighlights(list, props)).toEqual([{ key: 'director' }]);
	});

	it('keeps only the first three', () => {
		const list = ['director', 'year', 'seen', 'released'].map((key) => ({ key }));
		expect(normaliseHighlights(list, props).map((e) => e.key)).toEqual([
			'director',
			'year',
			'seen'
		]);
		expect(MAX_HIGHLIGHTS).toBe(3);
	});

	it('handles an absent list', () => {
		expect(normaliseHighlights(undefined, props)).toEqual([]);
	});
});

describe('highlight rank helpers', () => {
	it('toggles on at the end and off with renumbering', () => {
		let ranks: (number | undefined)[] = [undefined, undefined, undefined];
		ranks = toggledRanks(ranks, 2);
		ranks = toggledRanks(ranks, 0);
		expect(ranks).toEqual([2, undefined, 1]);
		expect(toggledRanks(ranks, 2)).toEqual([1, undefined, undefined]);
	});

	it('ignores turning one on at the limit', () => {
		const full = [1, 2, 3, undefined];
		expect(canHighlightMore(full)).toBe(false);
		expect(toggledRanks(full, 3)).toEqual(full);
		expect(toggledRanks(full, 1)).toEqual([1, undefined, 2, undefined]);
	});

	it('moves a highlighted field earlier or later, and stops at the ends', () => {
		const ranks = [1, undefined, 2, 3];
		expect(movedRanks(ranks, 2, -1)).toEqual([2, undefined, 1, 3]);
		expect(movedRanks(ranks, 2, 1)).toEqual([1, undefined, 3, 2]);
		expect(movedRanks(ranks, 0, -1)).toEqual(ranks);
		expect(movedRanks(ranks, 3, 1)).toEqual(ranks);
		expect(movedRanks(ranks, 1, 1)).toEqual(ranks);
	});
});

describe('schema round trip through the editor', () => {
	it('loads ranks, and writes the same list back', () => {
		const schema = schemaWith([{ key: 'stars' }, { key: 'director' }]);
		const items = schemaToItems(schema) as EditorField[];
		expect(items.find((f) => f.key === 'stars')?.highlight).toBe(1);
		expect(items.find((f) => f.key === 'director')?.highlight).toBe(2);
		expect(items.find((f) => f.key === 'year')?.highlight).toBeUndefined();
		const written = itemsToSchema(items, readSchemaMeta(schema));
		expect(readHighlights(written)).toEqual([{ key: 'stars' }, { key: 'director' }]);
	});

	it('writes highlights in rank order and resolves the key of a new field', () => {
		const a = field('a', 'text', { label: 'Director', keyPending: true, highlight: 2 });
		const b = field('b', 'rating', { label: 'Stars', keyPending: true, highlight: 1 });
		const written = itemsToSchema([a, b], {});
		expect(readHighlights(written)).toEqual([{ key: 'stars' }, { key: 'director' }]);
	});

	it('omits highlights entirely when none are set, but keeps other highlight lists', () => {
		const items = [field('a', 'text')];
		expect(readSchemaMeta(itemsToSchema(items, {})).highlights).toBeUndefined();
		const kept = itemsToSchema(items, { highlights: { connection: [{ key: 'role' }] } });
		expect(readSchemaMeta(kept).highlights).toEqual({ connection: [{ key: 'role' }] });
	});

	it('drops a field that is archived or switched to a non-highlightable kind', () => {
		const archived = archiveField(field('a', 'text', { highlight: 1 }));
		const kept = field('b', 'text', { highlight: 2 });
		expect(readHighlights(itemsToSchema([kept], {}, [archived]))).toEqual([{ key: 'b' }]);
		expect(readHighlights(itemsToSchema([field('n', 'longtext', { highlight: 1 })], {}))).toEqual(
			[]
		);
		expect(archived.highlight).toBeUndefined();
	});

	it('withHighlights replaces the card list and keeps unknown members', () => {
		const base = { 'x-menagerist': { version: 1, highlights: { card: [{ key: 'x' }], other: 1 } } };
		const next = withHighlights(base, [{ key: 'y' }]);
		expect(readSchemaMeta(next).highlights).toEqual({ card: [{ key: 'y' }], other: 1 });
		expect(readSchemaMeta(withHighlights(base, [])).highlights).toEqual({ other: 1 });
	});

	it('highlightRanks ignores dangling entries', () => {
		const ranks = highlightRanks(schemaWith([{ key: 'nope' }, { key: 'year' }]));
		expect([...ranks]).toEqual([['year', 1]]);
	});

	it('readHighlights skips malformed entries', () => {
		const schema = {
			'x-menagerist': { highlights: { card: [{ key: 'a' }, 'b', { key: 5 }, null] } }
		};
		expect(readHighlights(schema)).toEqual([{ key: 'a' }]);
		expect(readHighlights({ 'x-menagerist': { highlights: { card: 'a' } } })).toEqual([]);
		expect(readHighlights(null)).toEqual([]);
	});
});

describe('summaryItems', () => {
	const schema = schemaWith([{ key: 'director' }, { key: 'stars' }, { key: 'released' }]);

	it('lists values in the type order, formatted', () => {
		const items = summaryItems(
			{ director: 'Ridley Scott', stars: 4, released: '1979-05-25' },
			schema,
			'list'
		);
		expect(items.map((i) => i.key)).toEqual(['director', 'stars', 'released']);
		expect(items[0].text).toBe('Ridley Scott');
		expect(items[1].text).toBe('4');
		expect(items[2].text).not.toBe('1979-05-25');
		expect(items[2].text).toContain('1979');
	});

	it('applies each surface limit', () => {
		const attrs = { director: 'R', stars: 4, released: '1979-05-25' };
		for (const surface of ['grid', 'list', 'picker', 'row'] as const) {
			expect(summaryItems(attrs, schema, surface)).toHaveLength(
				Math.min(SURFACE_LIMITS[surface], 3)
			);
		}
	});

	it('skips empty values without leaving a gap, and counts only shown ones against the limit', () => {
		const items = summaryItems({ director: '', released: '1979-05-25', stars: 4 }, schema, 'grid');
		expect(items.map((i) => i.key)).toEqual(['stars', 'released']);
		expect(summaryItems({}, schema, 'list')).toEqual([]);
		expect(summaryItems({ director: null }, schema, 'list')).toEqual([]);
	});

	it('shows a boolean only when true', () => {
		const flags = schemaWith([{ key: 'seen' }]);
		expect(summaryItems({ seen: false }, flags, 'list')).toEqual([]);
		expect(summaryItems({ seen: true }, flags, 'list')).toHaveLength(1);
	});

	it('shows nothing without a type schema, attributes or highlights', () => {
		expect(summaryItems({ director: 'x' }, null, 'list')).toEqual([]);
		expect(summaryItems(null, schema, 'list')).toEqual([]);
		expect(summaryItems({ director: 'x' }, schemaWith([]), 'list')).toEqual([]);
	});

	it('ignores highlights that no longer apply', () => {
		const stale = schemaWith([{ key: 'old' }, { key: 'notes' }, { key: 'director' }]);
		expect(summaryItems({ old: 'a', notes: 'b', director: 'c' }, stale, 'list')).toHaveLength(1);
	});
});

describe('example fixture', () => {
	it('carries card highlights that are all valid', () => {
		const schema = JSON.parse(
			readFileSync(
				new URL('../../docs/field-types-spec/example-node-type-schema.json', import.meta.url),
				'utf-8'
			)
		) as AttributesSchema;
		const stored = readHighlights(schema);
		expect(stored.length).toBeGreaterThan(0);
		expect(normaliseHighlights(stored, schema.properties)).toEqual(stored);
	});
});

describe('connection highlights', () => {
	const edgeSchema = {
		$schema: 'https://json-schema.org/draft/2020-12/schema',
		type: 'object',
		properties: {
			date: { title: 'Date', type: 'string', format: 'date' },
			signed_by: { title: 'Signed by', type: 'string' },
			place: { title: 'Place', type: 'string' },
			old: { title: 'Old', type: 'string', 'x-menagerist': { kind: 'text', archived: true } }
		},
		'x-menagerist': {
			version: 1,
			highlights: {
				card: [{ key: 'place' }],
				connection: [{ key: 'date' }, { key: 'signed_by' }, { key: 'place' }]
			}
		}
	} as unknown as AttributesSchema;

	it('reads and writes the connection list without touching the card list', () => {
		expect(readHighlights(edgeSchema, 'connection').map((e) => e.key)).toEqual([
			'date',
			'signed_by',
			'place'
		]);
		const next = withHighlights(edgeSchema, [{ key: 'signed_by' }], 'connection');
		expect(readHighlights(next, 'connection')).toEqual([{ key: 'signed_by' }]);
		expect(readHighlights(next, 'card')).toEqual([{ key: 'place' }]);
		const cleared = withHighlights(next, [], 'connection');
		expect(readSchemaMeta(cleared).highlights).toEqual({ card: [{ key: 'place' }] });
	});

	it('allows two connection highlights', () => {
		expect(MAX_CONNECTION_HIGHLIGHTS).toBe(2);
		const props = edgeSchema.properties;
		const three = ['date', 'signed_by', 'place'].map((key) => ({ key }));
		expect(
			normaliseHighlights(three, props, maxHighlights('connection')).map((e) => e.key)
		).toEqual(['date', 'signed_by']);
		expect(highlightRanks(edgeSchema, 'connection').size).toBe(2);
		expect(toggledRanks([1, 2, undefined], 2, 2)).toEqual([1, 2, undefined]);
		expect(canHighlightMore([1, 2], 2)).toBe(false);
	});

	it('summarises a connection from its own list, up to two values', () => {
		const items = summaryItems(
			{ date: '2024-03-12', signed_by: 'Bryan Cranston', place: 'London' },
			edgeSchema,
			'connection'
		);
		expect(items.map((i) => i.key)).toEqual(['date', 'signed_by']);
		expect(items[1].text).toBe('Bryan Cranston');
		const card = summaryItems({ place: 'London' }, edgeSchema, 'list');
		expect(card.map((i) => i.key)).toEqual(['place']);
	});

	it('shows nothing when a connection has no highlighted values', () => {
		expect(summaryItems({}, edgeSchema, 'connection')).toEqual([]);
		expect(summaryItems({ date: '2024-03-12' }, null, 'connection')).toEqual([]);
	});

	it('writes the connection list from the editor and leaves the card list', () => {
		const items = schemaToItems(edgeSchema, 'connection') as EditorField[];
		expect(items.find((f) => f.key === 'date')?.highlight).toBe(1);
		expect(items.find((f) => f.key === 'place')?.highlight).toBeUndefined();
		const written = itemsToSchema(items, readSchemaMeta(edgeSchema), [], 'connection');
		expect(readHighlights(written, 'connection').map((e) => e.key)).toEqual(['date', 'signed_by']);
		expect(readHighlights(written, 'card')).toEqual([{ key: 'place' }]);
	});
});
