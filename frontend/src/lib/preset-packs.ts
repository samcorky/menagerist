import { generateFieldKey } from '$lib/field-key';
import type { AttributesSchema, JsonSchemaProperty } from '$lib/schema-types';
import { withPropMeta } from '$lib/schema-meta';
import {
	exportBundle,
	listPresets,
	type BundleFileResponse,
	type BundlePresetEntry,
	type PresetResponse
} from '$lib/api/client';

/** The `menagerist-bundle` file format: saved fields, lists and groups, and item types. */
export const BUNDLE_FORMAT = 'menagerist-bundle';

/** A bundle file of presets, as exported and as read back for import. */
export type PresetBundle = BundleFileResponse;

/** The server takes at most this many ids per export request. */
export const EXPORT_CHUNK = 200;
const PAGE_SIZE = 50;

/** Whether a preset's options can be edited here: only choice lists have options. */
export function canEditOptions(preset: PresetResponse): boolean {
	return preset.kind === 'choice_list';
}

/** Read every live preset of every kind, following the Link header's next cursor. */
export async function fetchAllPresets(): Promise<PresetResponse[]> {
	const all: PresetResponse[] = [];
	let after: string | undefined;
	for (;;) {
		const result = await listPresets({ query: { after, limit: PAGE_SIZE } });
		if (result.error || !result.data) throw result.error ?? new Error('Could not list presets');
		all.push(...result.data);
		const hasNext = /rel="next"/.test(result.response?.headers.get('link') ?? '');
		if (!hasNext || result.data.length === 0) return all;
		after = result.data[result.data.length - 1].id;
	}
}

/**
 * Export the given presets as one bundle file, in chunks the server accepts. Each
 * preset's ref is its id, so chunks never clash.
 */
export async function exportPresetBundle(presets: PresetResponse[]): Promise<PresetBundle> {
	const all: BundlePresetEntry[] = [];
	for (let i = 0; i < presets.length; i += EXPORT_CHUNK) {
		const ids = presets.slice(i, i + EXPORT_CHUNK).map((p) => p.id);
		const result = await exportBundle({ query: { preset_ids: ids } });
		if (result.error || !result.data) throw result.error ?? new Error('Could not export presets');
		all.push(...result.data.presets);
	}
	return {
		format: BUNDLE_FORMAT,
		version: 2,
		presets: all,
		relationship_types: [],
		item_types: []
	};
}

/** Export item types, with the saved lists their fields use, as one bundle file. */
export async function exportTypeBundle(typeIds: string[]): Promise<PresetBundle> {
	const result = await exportBundle({ query: { item_type_ids: typeIds } });
	if (result.error || !result.data) throw result.error ?? new Error('Could not export the type');
	return result.data;
}

/** Export one connection type, with the saved lists its fields use, as a bundle file. */
export async function exportConnectionTypeBundle(typeId: string): Promise<PresetBundle> {
	const result = await exportBundle({ query: { relationship_type_ids: [typeId] } });
	if (result.error || !result.data) throw result.error ?? new Error('Could not export the type');
	return result.data;
}

/** Parse a bundle file's text, checking only the envelope. The server validates the rest. */
export function parseBundleText(text: string): PresetBundle {
	let data: unknown;
	try {
		data = JSON.parse(text);
	} catch {
		throw new Error("This file isn't valid JSON");
	}
	if (
		typeof data !== 'object' ||
		data === null ||
		(data as { format?: unknown }).format !== BUNDLE_FORMAT ||
		!Array.isArray((data as { presets?: unknown }).presets)
	) {
		throw new Error("This isn't a Menagerist saved fields file");
	}
	return data as PresetBundle;
}

/** Trigger a browser download of a bundle as a JSON file. */
export function downloadBundle(
	bundle: PresetBundle,
	filename = 'menagerist-saved-fields.json'
): void {
	const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: 'application/json' });
	const url = URL.createObjectURL(blob);
	const anchor = document.createElement('a');
	anchor.href = url;
	anchor.download = filename;
	anchor.click();
	URL.revokeObjectURL(url);
}

/** The kind a section holds. Its import and export only handle presets of this kind. */
export type PackSectionKind = PresetResponse['kind'];

/** A message when a bundle holds presets of other kinds, or null when every one fits the section. */
export function bundleKindMismatch(bundle: PresetBundle, kind: PackSectionKind): string | null {
	const others = bundle.presets.filter((preset) => preset.kind !== kind).length;
	if (others === 0) return null;
	const noun = kindNoun(kind, others);
	return others === 1
		? `1 item in this file is not a ${noun}`
		: `${others} items in this file are not ${noun}`;
}

/** A readable name for a kind; `count` picks the plural. */
export function kindNoun(kind: PackSectionKind, count: number): string {
	const names: Record<PackSectionKind, [singular: string, plural: string]> = {
		field: ['field', 'fields'],
		field_set: ['field group', 'field groups'],
		choice_list: ['list', 'lists']
	};
	return count === 1 ? names[kind][0] : names[kind][1];
}

/** A safe file name for one preset's export, e.g. "Condition grades.json". */
export function presetFilename(label: string): string {
	const safe =
		label
			.replace(/[/:*?"<>|]+/g, ' ')
			.replace(/\s+/g, ' ')
			.trim() || 'preset';
	return `${safe}.json`;
}

/**
 * A schema that previews a preset with the normal attributes editor: one field for a
 * field or a list, one per property for a field group. Keys come from the labels.
 */
export function presetExampleSchema(preset: PresetResponse): AttributesSchema {
	const properties: Record<string, JsonSchemaProperty> = {};
	const add = (property: JsonSchemaProperty) => {
		const title = typeof property.title === 'string' ? property.title : preset.label;
		properties[generateFieldKey(title, Object.keys(properties))] = property;
	};
	const definition = preset.definition as Record<string, unknown>;

	if (preset.kind === 'field') {
		add(definition.property as JsonSchemaProperty);
	} else if (preset.kind === 'choice_list') {
		const options = Array.isArray(definition.options) ? definition.options : [];
		add(
			withPropMeta(
				{
					title: preset.label,
					type: 'string',
					enum: options.filter((o): o is string => typeof o === 'string')
				},
				{ kind: 'choice' }
			)
		);
	} else {
		const group = definition.properties;
		for (const property of Array.isArray(group) ? group : []) add(property as JsonSchemaProperty);
	}

	return { $schema: 'https://json-schema.org/draft/2020-12/schema', type: 'object', properties };
}
