import { normalise, isSectionItem, type XLayout } from '$lib/layout';
import type { JsonSchemaProperty, AttributesSchema, EditorField } from '$lib/schema-types';
import { fieldFromProperty, propertyFromField } from '$lib/field-types';
import { resolvePendingKeys } from '$lib/field-key';
import {
	META_VERSION,
	archivedKeys,
	readSchemaMeta,
	withHighlights,
	withSchemaMeta,
	type HighlightList,
	type SchemaMeta
} from '$lib/schema-meta';
import {
	highlightColumnChoices,
	highlightRanks,
	maxHighlights,
	normaliseHighlights
} from '$lib/highlights';

export type EditorSection = {
	_section: true;
	id: string;
	sectionLabel: string;
	fields: EditorField[];
};

export type EditorItem = EditorField | EditorSection;

export function isSection(item: EditorItem): item is EditorSection {
	return '_section' in item;
}

export function schemaToItems(
	schema: AttributesSchema | null,
	list: HighlightList = 'card'
): EditorItem[] {
	if (!schema) return [];
	const required = new Set(readSchemaMeta(schema).required ?? []);
	const layout = normalise(readSchemaMeta(schema).layout, schema.properties);
	const ranks = highlightRanks(schema, list);
	const columns = highlightColumnChoices(schema, list);
	const load = (key: string): EditorField => {
		const field = fieldFromProperty(key, schema.properties[key], required.has(key));
		const rank = ranks.get(key);
		if (rank === undefined) return field;
		const column = columns.get(key);
		return column === undefined
			? { ...field, highlight: rank }
			: { ...field, highlight: rank, highlightColumn: column };
	};
	return layout.flatMap((layoutItem): EditorItem[] => {
		if (isSectionItem(layoutItem)) {
			return [
				{
					_section: true,
					id: layoutItem.id,
					sectionLabel: layoutItem.section,
					fields: layoutItem.items.filter((i) => i.key in schema.properties).map((i) => load(i.key))
				}
			];
		}
		if (!(layoutItem.key in schema.properties)) return [];
		return [load(layoutItem.key)];
	});
}

export function schemaToArchived(schema: AttributesSchema | null): EditorField[] {
	if (!schema) return [];
	const required = new Set(readSchemaMeta(schema).required ?? []);
	return [...archivedKeys(schema)].map((key) =>
		fieldFromProperty(key, schema.properties[key], required.has(key))
	);
}

/**
 * The schema as the schema editor writes it back the moment it opens `schema`: the same fields,
 * with the layout, version and highlights it keeps filled in. Opening an editor with this, not
 * the stored schema, makes what the form holds when it opens equal to what it holds a moment
 * later, so an untouched editor is not mistaken for a changed one. `list` is the highlight list
 * the editor is given.
 */
export function settleSchema(
	schema: AttributesSchema | null,
	list: HighlightList = 'card'
): AttributesSchema | null {
	return itemsToSchema(
		schemaToItems(schema, list),
		readSchemaMeta(schema),
		schemaToArchived(schema),
		list
	);
}

export function itemsToSchema(
	items: EditorItem[],
	baseMeta: SchemaMeta,
	archived: EditorField[] = [],
	list: HighlightList = 'card'
): AttributesSchema | null {
	// Resolve pending keys across the whole schema so they are unique globally.
	// Archived fields are included so they keep occupying their keys.
	const visible = items.flatMap((item) => (isSection(item) ? item.fields : [item]));
	const all = [...visible, ...archived];
	const resolvedList = resolvePendingKeys(all);
	const resolved = new Map(all.map((f, i) => [f, resolvedList[i]]));

	const entries: [string, JsonSchemaProperty][] = [];
	const required: string[] = [];
	const layout: XLayout = [];

	for (const item of items) {
		if (isSection(item)) {
			const sectionLayout: { key: string }[] = [];
			for (const original of item.fields) {
				const f = resolved.get(original)!;
				if (!f.key) continue;
				entries.push([f.key, propertyFromField(f)]);
				if (f.required) required.push(f.key);
				sectionLayout.push({ key: f.key });
			}
			if (sectionLayout.length > 0) {
				layout.push({
					id: item.id,
					section: item.sectionLabel || 'Section',
					items: sectionLayout
				});
			}
		} else {
			const f = resolved.get(item)!;
			if (!f.key) continue;
			entries.push([f.key, propertyFromField(f)]);
			if (f.required) required.push(f.key);
			layout.push({ key: f.key });
		}
	}

	for (const original of archived) {
		const f = resolved.get(original)!;
		if (f.key) entries.push([f.key, propertyFromField(f)]);
	}

	if (entries.length === 0) return null;
	const base = {
		$schema: 'https://json-schema.org/draft/2020-12/schema' as const,
		type: 'object' as const,
		properties: Object.fromEntries(entries) as Record<string, JsonSchemaProperty>
	};
	const card = visible
		.filter((f) => f.highlight !== undefined)
		.sort((a, b) => a.highlight! - b.highlight!)
		.map((f) => ({
			key: resolved.get(f)!.key,
			...(f.highlightColumn !== undefined && { column: f.highlightColumn })
		}));
	const withMeta = withSchemaMeta(base, {
		...baseMeta,
		version: META_VERSION,
		layout,
		required
	});
	return withHighlights(
		withMeta,
		normaliseHighlights(card, base.properties, maxHighlights(list)),
		list
	);
}
