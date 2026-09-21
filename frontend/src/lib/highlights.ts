import { descriptorForProp } from '$lib/field-types';
import {
	archivedKeys,
	readHighlights,
	type HighlightEntry,
	type HighlightList
} from '$lib/schema-meta';
import type { AttributesSchema, JsonSchemaProperty } from '$lib/schema-types';

/** Most fields a type may show on its cards, and a relationship type on its connection rows. */
export const MAX_HIGHLIGHTS = 3;
export const MAX_CONNECTION_HIGHLIGHTS = 2;

export function maxHighlights(list: HighlightList): number {
	return list === 'connection' ? MAX_CONNECTION_HIGHLIGHTS : MAX_HIGHLIGHTS;
}

export type Surface = 'grid' | 'list' | 'picker' | 'row' | 'connection';

/** How many highlighted values each surface shows; the cover and title keep priority (§3.2). */
export const SURFACE_LIMITS: Record<Surface, number> = {
	grid: 2,
	list: 3,
	picker: 1,
	row: 2,
	connection: 2
};

export function isHighlightable(prop: JsonSchemaProperty | undefined): boolean {
	return prop !== undefined && descriptorForProp(prop)?.highlightable === true;
}

/**
 * Clean a stored highlight list: drops dangling keys, archived and non-highlightable
 * properties, duplicates, and anything past the limit.
 */
export function normaliseHighlights(
	list: HighlightEntry[] | undefined,
	properties: Record<string, JsonSchemaProperty>,
	max = MAX_HIGHLIGHTS
): HighlightEntry[] {
	const archived = archivedKeys({ properties });
	const seen = new Set<string>();
	const result: HighlightEntry[] = [];
	for (const { key } of list ?? []) {
		if (result.length >= max) break;
		if (seen.has(key) || !Object.hasOwn(properties, key) || archived.has(key)) continue;
		if (!isHighlightable(properties[key])) continue;
		seen.add(key);
		result.push({ key });
	}
	return result;
}

/** 1-based rank of each highlighted key in a schema, for loading the editor. */
export function highlightRanks(
	schema: AttributesSchema | null,
	list: HighlightList = 'card'
): Map<string, number> {
	if (!schema) return new Map();
	return new Map(
		normaliseHighlights(readHighlights(schema, list), schema.properties, maxHighlights(list)).map(
			(e, i) => [e.key, i + 1]
		)
	);
}

function renumber(ranks: (number | undefined)[]): (number | undefined)[] {
	const order = ranks
		.map((rank, index) => ({ rank, index }))
		.filter((r): r is { rank: number; index: number } => r.rank !== undefined)
		.sort((a, b) => a.rank - b.rank);
	const out: (number | undefined)[] = ranks.map(() => undefined);
	order.forEach((r, i) => (out[r.index] = i + 1));
	return out;
}

/** Whether another field may still be highlighted. */
export function canHighlightMore(ranks: (number | undefined)[], max = MAX_HIGHLIGHTS): boolean {
	return ranks.filter((r) => r !== undefined).length < max;
}

/** Ranks after toggling the field at `index`. Turning one on is ignored at the limit. */
export function toggledRanks(
	ranks: (number | undefined)[],
	index: number,
	max = MAX_HIGHLIGHTS
): (number | undefined)[] {
	const next = [...ranks];
	if (next[index] !== undefined) {
		next[index] = undefined;
		return renumber(next);
	}
	if (!canHighlightMore(ranks, max)) return ranks;
	next[index] = Math.max(0, ...ranks.filter((r): r is number => r !== undefined)) + 1;
	return next;
}

/** Ranks after moving the highlighted field at `index` one place earlier (-1) or later (1). */
export function movedRanks(
	ranks: (number | undefined)[],
	index: number,
	direction: -1 | 1
): (number | undefined)[] {
	const rank = ranks[index];
	if (rank === undefined) return ranks;
	const other = ranks.findIndex((r) => r === rank + direction);
	if (other === -1) return ranks;
	const next = [...ranks];
	next[index] = rank + direction;
	next[other] = rank;
	return next;
}

export type SummaryItem = {
	key: string;
	label: string;
	prop: JsonSchemaProperty;
	value: unknown;
	/** Plain-text form, used when the type has no compact widget. */
	text: string;
};

function isEmpty(value: unknown, prop: JsonSchemaProperty): boolean {
	if (value === undefined || value === null || value === '') return true;
	return prop.type === 'boolean' && value !== true && value !== 'true';
}

/**
 * The highlighted values to show for an item on a surface: in the type's order, with empty
 * values skipped and the surface's limit applied.
 */
export function summaryItems(
	attributes: Record<string, unknown> | null | undefined,
	schema: AttributesSchema | null | undefined,
	surface: Surface
): SummaryItem[] {
	if (!schema || !attributes) return [];
	const items: SummaryItem[] = [];
	const list: HighlightList = surface === 'connection' ? 'connection' : 'card';
	const entries = normaliseHighlights(
		readHighlights(schema, list),
		schema.properties,
		maxHighlights(list)
	);
	for (const { key } of entries) {
		if (items.length >= SURFACE_LIMITS[surface]) break;
		const prop = schema.properties[key];
		const value = attributes[key];
		if (isEmpty(value, prop)) continue;
		const text = descriptorForProp(prop)?.formatSummary?.(value, prop) ?? String(value);
		if (text === '') continue;
		items.push({ key, label: prop.title || key, prop, value, text });
	}
	return items;
}
