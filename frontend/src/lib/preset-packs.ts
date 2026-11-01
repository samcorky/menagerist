import { generateFieldKey } from '$lib/field-key';
import type { AttributesSchema, JsonSchemaProperty } from '$lib/schema-types';
import { withPropMeta } from '$lib/schema-meta';
import {
	exportPresets,
	listPresets,
	type PackResponse,
	type PresetResponse
} from '$lib/api/client';

/** The server takes at most this many ids per export request. */
export const EXPORT_CHUNK = 200;
const PAGE_SIZE = 50;

/** The label given to a copy of a preset, e.g. "Condition grades (copy)". */
export function copyLabel(label: string): string {
	return `${label} (copy)`;
}

/** Whether a preset's options can be edited here: only copies and custom lists, never built-ins. */
export function canEditOptions(preset: PresetResponse): boolean {
	return preset.kind === 'choice_list' && !preset.builtin;
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

/** Export the given presets as one pack, in chunks the server accepts. */
export async function exportPack(presets: PresetResponse[]): Promise<PackResponse> {
	const items: PackResponse['items'] = [];
	for (let i = 0; i < presets.length; i += EXPORT_CHUNK) {
		const ids = presets.slice(i, i + EXPORT_CHUNK).map((p) => p.id);
		const result = await exportPresets({ query: { ids } });
		if (result.error || !result.data) throw result.error ?? new Error('Could not export presets');
		items.push(...result.data.items);
	}
	return { format: 'menagerist-presets', version: 1, items };
}

/** Parse a pack file's text, checking only the envelope. The server validates the rest. */
export function parsePackText(text: string): PackResponse {
	let data: unknown;
	try {
		data = JSON.parse(text);
	} catch {
		throw new Error("This file isn't valid JSON");
	}
	if (
		typeof data !== 'object' ||
		data === null ||
		(data as { format?: unknown }).format !== 'menagerist-presets' ||
		!Array.isArray((data as { items?: unknown }).items)
	) {
		throw new Error("This isn't a Menagerist presets file");
	}
	return data as PackResponse;
}

/** Trigger a browser download of a pack as a JSON file. */
export function downloadPack(pack: PackResponse, filename = 'menagerist-presets.json'): void {
	const blob = new Blob([JSON.stringify(pack, null, 2)], { type: 'application/json' });
	const url = URL.createObjectURL(blob);
	const anchor = document.createElement('a');
	anchor.href = url;
	anchor.download = filename;
	anchor.click();
	URL.revokeObjectURL(url);
}

/** The kind a section holds. Its import and export only handle presets of this kind. */
export type PackSectionKind = PresetResponse['kind'];

/** A message when a pack holds presets of other kinds, or null when every item fits the section. */
export function packKindMismatch(pack: PackResponse, kind: PackSectionKind): string | null {
	const others = pack.items.filter((item) => item.kind !== kind).length;
	if (others === 0) return null;
	return `${others} ${others === 1 ? 'item in this file is' : 'items in this file are'} not ${kindNoun(kind, others)}`;
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

const SHOW_BUILTINS_KEY = 'menagerist.presets.showBuiltins';

/** Whether built-in presets are shown. Defaults to shown; a private window may refuse storage. */
export function readShowBuiltins(): boolean {
	try {
		return localStorage.getItem(SHOW_BUILTINS_KEY) !== 'false';
	} catch {
		return true;
	}
}

export function writeShowBuiltins(show: boolean): void {
	try {
		localStorage.setItem(SHOW_BUILTINS_KEY, String(show));
	} catch {
		// Storage unavailable: the choice applies to this page only.
	}
}

/** Drop built-in presets when they are hidden. */
export function visiblePresets<T extends { builtin: boolean }>(
	presets: T[],
	showBuiltins: boolean
): T[] {
	return showBuiltins ? presets : presets.filter((p) => !p.builtin);
}
