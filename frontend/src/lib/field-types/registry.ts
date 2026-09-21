import type { Component } from 'svelte';
import type { JsonSchemaProperty, EditorField } from '$lib/schema-types';
import { readPropMeta, withPropMeta } from '$lib/schema-meta';

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

export type FieldTypeDescriptor = {
	kind: string;
	/** Human-readable label shown in the kind dropdown. */
	label: string;
	/**
	 * Whether this type may appear as a group sub-field.
	 * Defaults to true; set false for types that cannot nest (group, choice).
	 */
	canBeSubField?: boolean;
	/** Set false to hide the kind from the kind dropdowns (e.g. `opaque`). */
	selectable?: boolean;
	/** Presentation settings offered in the schema editor; widgets read them from the property. */
	displayOptions?: DisplayOption[];
	/**
	 * Friendly wording for a failed validation keyword (for example a `pattern` written by this
	 * type), or null to fall back to the validator's own message. Used for client and server errors.
	 */
	formatError?: (keyword: string, value: unknown) => string | null;
	/** Whether attribute search reads values of this type. Defaults to true. */
	searchable?: boolean;
	/** Whether a field of this type may be shown on cards. Defaults to false. */
	highlightable?: boolean;
	/** Plain text for a highlighted value; null skips it. Defaults to `String(value)`. */
	formatSummary?: (value: unknown, prop: JsonSchemaProperty) => string | null;
	/** Compact rendering of a highlighted value on a card. Falls back to `formatSummary`. */
	SummaryWidget?: Component<{ value: unknown; prop: JsonSchemaProperty; size: 'sm' | 'md' }>;
	/** Serialise an EditorField to a JSON Schema property. */
	toSchema: (field: EditorField) => JsonSchemaProperty;
	/**
	 * Attempt to deserialise a JSON Schema property into an EditorField.
	 * Return null if this descriptor does not match the property shape.
	 */
	fromSchema: (key: string, prop: JsonSchemaProperty, required: boolean) => EditorField | null;
	/**
	 * Optional extra controls rendered below the field row in schema-editor
	 * (e.g. options list for choice, sub-field list for group).
	 */
	EditorExtras?: Component<{ field: EditorField; onChange: (f: EditorField) => void }>;
	/** Widget rendered inside attributes-editor for data entry. */
	InputWidget: Component<{
		value: unknown;
		onChange: (v: unknown) => void;
		ariaLabel: string;
		prop: JsonSchemaProperty;
	}>;
	/** Optional widget for read-mode display. Falls back to String(value) when absent. */
	ViewWidget?: Component<{ value: unknown; prop: JsonSchemaProperty }>;
};

const registry = new Map<string, FieldTypeDescriptor>();

export function register(d: FieldTypeDescriptor): void {
	registry.set(d.kind, d);
}

export function getDescriptor(kind: string): FieldTypeDescriptor | undefined {
	return registry.get(kind);
}

export function allDescriptors(): FieldTypeDescriptor[] {
	return [...registry.values()];
}

/**
 * Find the descriptor for a property. An explicit `kind` in the property metadata is a direct lookup
 * (and must still match the property's shape); otherwise the first descriptor whose
 * fromSchema matches wins, so registration order in index.ts sets precedence.
 */
export function descriptorForProp(prop: JsonSchemaProperty): FieldTypeDescriptor | undefined {
	const kind = readPropMeta(prop).kind;
	if (kind !== undefined) {
		const desc = registry.get(kind);
		return desc && desc.fromSchema('_', prop, false) !== null ? desc : undefined;
	}
	for (const desc of registry.values()) {
		if (desc.fromSchema('_', prop, false) !== null) return desc;
	}
	return undefined;
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

/** Remove all registrations — for use in tests only. */
export function _clearRegistry(): void {
	registry.clear();
}
