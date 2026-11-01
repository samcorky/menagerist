import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { descriptorForProp, fieldFromProperty } from '../src/lib/field-types';
import type { JsonSchemaProperty } from '../src/lib/schema-types';

type Schema = { properties?: Record<string, JsonSchemaProperty> } | null | undefined;
type Typed = { ref: string; slug: string; attributes_schema?: Schema };
type Pack = {
	id: string;
	requires?: string[];
	presets?: { ref: string; definition: { options?: string[] } }[];
	item_types?: Typed[];
	relationship_types?: Typed[];
	items?: { ref: string; type: string; attributes?: Record<string, unknown> }[];
	connections?: { from: string; to: string; type: string; attributes?: Record<string, unknown> }[];
};

const DUMMY_ID = '00000000-0000-7000-8000-000000000000';

function readJson(name: string): unknown {
	return JSON.parse(
		readFileSync(
			new URL(`../../backend/src/app/modules/examples/packs/${name}`, import.meta.url),
			'utf8'
		)
	);
}

// The installer swaps `{"$preset": ref}` for a real id; do the same with a dummy.
function resolvePresets(value: unknown): unknown {
	if (Array.isArray(value)) return value.map(resolvePresets);
	if (value !== null && typeof value === 'object') {
		const entries = Object.entries(value);
		if (entries.length === 1 && entries[0][0] === '$preset') return DUMMY_ID;
		return Object.fromEntries(entries.map(([k, v]) => [k, resolvePresets(v)]));
	}
	return value;
}

const index = readJson('index.json') as { packs: { id: string }[] };
const packs = index.packs.map((p) => readJson(`${p.id}.json`) as Pack);
const packsById = new Map(packs.map((p) => [p.id, p] as const));

// An add-on names its required packs' types as `pack:ref`; list them beside its own.
function typesByRef(pack: Pack, pick: (p: Pack) => Typed[] | undefined): Map<string, Typed> {
	const all = new Map((pick(pack) ?? []).map((t) => [t.ref, t] as const));
	for (const required of pack.requires ?? []) {
		for (const t of pick(packsById.get(required) as Pack) ?? []) all.set(`${required}:${t.ref}`, t);
	}
	return all;
}

// The API fills a linked choice's `enum` from its list on read; do the same from the pack's preset.
function fillLinkedChoices(schema: Schema, pack: Pack): Schema {
	for (const prop of Object.values(schema?.properties ?? {})) {
		const list = (prop['x-menagerist'] as { list?: { $preset?: string } } | undefined)?.list;
		const ref = list?.$preset;
		if (ref === undefined) continue;
		const options = pack.presets?.find((p) => p.ref === ref)?.definition.options;
		expect(options, `preset ${ref} has options`).toBeDefined();
		(prop as { enum?: string[] }).enum = options;
	}
	return schema;
}

function schemas(pack: Pack): { where: string; schema: Schema }[] {
	return [
		...(pack.item_types ?? []).map((t) => ({
			where: `${pack.id}/${t.slug}`,
			schema: t.attributes_schema
		})),
		...(pack.relationship_types ?? []).map((t) => ({
			where: `${pack.id}/${t.slug}`,
			schema: t.attributes_schema
		}))
	];
}

describe('shipped example packs', () => {
	it('lists at least one pack', () => {
		expect(packs.length).toBeGreaterThan(0);
	});

	describe.each(packs.map((p) => [p.id, p] as const))('%s', (_id, pack) => {
		it('uses only field kinds the UI can render', () => {
			for (const { where, schema } of schemas(pack)) {
				const filled = fillLinkedChoices(structuredClone(schema), pack);
				const resolved = resolvePresets(filled) as Schema;
				for (const [key, prop] of Object.entries(resolved?.properties ?? {})) {
					const at = `${where}.${key}`;
					const descriptor = descriptorForProp(prop);
					expect(descriptor, `${at} has no descriptor`).toBeDefined();
					const field = fieldFromProperty(key, prop, false);
					expect(field.kind, `${at} is opaque`).not.toBe('opaque');
					const columns =
						(prop as { items?: { properties?: Record<string, JsonSchemaProperty> } }).items
							?.properties ?? {};
					for (const sub of field.subFields) {
						expect(sub.kind, `${at}.${sub.key} is opaque`).not.toBe('opaque');
						expect(descriptorForProp(columns[sub.key]), `${at}.${sub.key}`).toBeDefined();
					}
					const stored = prop['x-menagerist']?.kind;
					if (stored !== undefined) {
						expect(stored, `${at} stored kind`).toBe(descriptor!.kind);
					}
				}
			}
		});

		it('only sets attributes its type defines', () => {
			const itemTypes = typesByRef(pack, (p) => p.item_types);
			const relationshipTypes = typesByRef(pack, (p) => p.relationship_types);
			const keysByItemType = new Map(
				[...itemTypes].map(([ref, t]) => [ref, Object.keys(t.attributes_schema?.properties ?? {})])
			);
			const keysByRelationship = new Map(
				[...relationshipTypes].map(([ref, t]) => [
					ref,
					Object.keys(t.attributes_schema?.properties ?? {})
				])
			);
			const schemaByItemType = new Map(
				[...itemTypes].map(([ref, t]) => [ref, t.attributes_schema])
			);
			for (const item of pack.items ?? []) {
				const known = keysByItemType.get(item.type) ?? [];
				for (const key of Object.keys(item.attributes ?? {})) {
					expect(known, `item ${item.ref}.${key}`).toContain(key);
				}
				// Table rows may only use the columns their property declares.
				const props = schemaByItemType.get(item.type)?.properties ?? {};
				for (const [key, value] of Object.entries(item.attributes ?? {})) {
					const meta = props[key]?.['x-menagerist'] as
						{ kind?: string; columns?: string[] } | undefined;
					if (meta?.kind !== 'group') continue;
					expect(Array.isArray(value), `item ${item.ref}.${key} is rows`).toBe(true);
					for (const [i, row] of (value as unknown[]).entries()) {
						const at = `item ${item.ref}.${key}[${i}]`;
						expect(row !== null && typeof row === 'object', `${at} is an object`).toBe(true);
						for (const col of Object.keys(row as object)) {
							expect(meta.columns ?? [], `${at}.${col}`).toContain(col);
						}
					}
				}
			}
			for (const c of pack.connections ?? []) {
				const known = keysByRelationship.get(c.type) ?? [];
				for (const key of Object.keys(c.attributes ?? {})) {
					expect(known, `connection ${c.from} -> ${c.to}.${key}`).toContain(key);
				}
			}
		});
	});
});
