import type { Component } from 'svelte';
import type { JsonSchemaProperty, EditorField } from '$lib/schema-types';

export type FieldTypeDescriptor = {
	kind: string;
	/** Human-readable label shown in the kind dropdown. */
	label: string;
	/**
	 * Whether this type may appear as a group sub-field.
	 * Defaults to true; set false for types that cannot nest (group, choice).
	 */
	canBeSubField?: boolean;
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
 * Return the first descriptor whose fromSchema returns non-null for the given prop.
 * Registration order in index.ts determines precedence (most-specific first).
 */
export function descriptorForProp(prop: JsonSchemaProperty): FieldTypeDescriptor | undefined {
	for (const desc of registry.values()) {
		if (desc.fromSchema('_', prop, false) !== null) return desc;
	}
	return undefined;
}

/** Remove all registrations — for use in tests only. */
export function _clearRegistry(): void {
	registry.clear();
}
