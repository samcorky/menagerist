import type { Component } from 'svelte';
import type { EditorField } from '$lib/schema-types';
import type { JsonSchemaProperty } from '$lib/json-schema';
import { readPropMeta, withPropMeta } from '$lib/prop-meta';
import { _clearCores, allCores, pickCore, registerCore, type FieldCore } from './core';

/** A per-field presentation setting, shown in the schema editor as a "Show as" style dropdown. */
export type DisplayOption = {
	/**
	 * Where the value lives: `display` is stored in the property metadata; any other key is
	 * editor state (`EditorField.config`) that the descriptor maps to a validation keyword.
	 */
	key: string;
	label: string;
	choices: { value: string; label: string }[];
	default: string;
};

/** The schema editor's half of a field type: how it is written to and read from a schema. */
export type FieldAuthoring = {
	/**
	 * Whether this type may appear as a group sub-field.
	 * Defaults to true; set false for types that cannot nest (group itself).
	 */
	canBeSubField?: boolean;
	/** Set false to hide the kind from the kind dropdowns (e.g. `opaque`). */
	selectable?: boolean;
	/** Presentation settings offered in the schema editor; widgets read them from the property. */
	displayOptions?: DisplayOption[];
	/** Whether attribute search reads values of this type. Defaults to true. */
	searchable?: boolean;
	/** Whether a field of this type may be shown on cards. Defaults to false. */
	highlightable?: boolean;
	/** Serialise an EditorField to a JSON Schema property. */
	toSchema: (field: EditorField) => JsonSchemaProperty;
	/**
	 * Attempt to deserialise a JSON Schema property into an EditorField.
	 * Return null if this descriptor does not match the property shape. A property matches
	 * the kind exactly when this returns non-null: the core's `matches` is derived from it.
	 */
	fromSchema: (key: string, prop: JsonSchemaProperty, required: boolean) => EditorField | null;
	/**
	 * Optional extra controls rendered below the field row in schema-editor
	 * (e.g. options list for choice, sub-field list for group).
	 */
	EditorExtras?: Component<{ field: EditorField; onChange: (f: EditorField) => void }>;
};

/** A kind with both halves, as registered by `register`. */
export type FieldTypeDescriptor = Omit<FieldCore, 'matches'> & FieldAuthoring;

const registry = new Map<string, FieldTypeDescriptor>();

/** Register both halves of a kind: the core everyone uses and the schema editor's descriptor. */
export function register(d: FieldTypeDescriptor): void {
	registerCore({
		kind: d.kind,
		label: d.label,
		matches: (prop) => d.fromSchema('_', prop, false) !== null,
		rank: d.rank,
		formatError: d.formatError,
		formatSummary: d.formatSummary,
		SummaryWidget: d.SummaryWidget,
		InputWidget: d.InputWidget,
		ViewWidget: d.ViewWidget
	});
	registry.set(d.kind, d);
}

export function getDescriptor(kind: string): FieldTypeDescriptor | undefined {
	return registry.get(kind);
}

export function allDescriptors(): FieldTypeDescriptor[] {
	return [...registry.values()];
}

/**
 * Find the descriptor for a property: the core match (see `pickCore`) among the kinds that have
 * a schema-editor half. A core-only kind is never returned here.
 */
export function descriptorForProp(prop: JsonSchemaProperty): FieldTypeDescriptor | undefined {
	const authored = allCores().filter((c) => registry.has(c.kind));
	const core = pickCore<FieldCore>(authored, prop);
	return core && registry.get(core.kind);
}

/** Build an EditorField from a property; anything unrecognised becomes `opaque`. */
export function fieldFromProperty(
	key: string,
	prop: JsonSchemaProperty,
	required: boolean
): EditorField {
	const desc = descriptorForProp(prop);
	const field = desc?.fromSchema(key, prop, required);
	if (desc && field) return { ...field, meta: readPropMeta(prop), originalKind: field.kind };
	return {
		key,
		label: prop.title,
		kind: 'opaque',
		required,
		options: [],
		subFields: [],
		raw: prop as Record<string, unknown>
	};
}

/** Serialise an EditorField, writing its `kind` and preserving its other metadata. */
export function propertyFromField(f: EditorField): JsonSchemaProperty {
	const desc = registry.get(f.kind);
	if (!desc) return { title: f.label, type: 'string' };
	const prop = desc.toSchema(f);
	return f.kind === 'opaque' ? prop : withPropMeta(prop, { ...f.meta, kind: f.kind });
}

/** Remove all registrations - for use in tests only. */
export function _clearRegistry(): void {
	registry.clear();
	_clearCores();
}
