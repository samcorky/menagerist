import { fieldFromProperty, propertyFromField } from '$lib/field-types';
import { readPropMeta, replacePropMeta, withPropMeta } from '$lib/schema-meta';
import type { EditorField, JsonSchemaProperty } from '$lib/schema-types';
import type { EditorSection } from '$lib/schema-editor-items';

/** A saved field, a named field group ("field group", `field_set` in code) or a list. */
export type PresetKind = 'field' | 'field_set' | 'choice_list';

export type Origin = { preset: string; version: number };

export type FieldDefinition = { property: JsonSchemaProperty };
export type ChoiceListDefinition = { options: string[] };
export type FieldSetDefinition = { section: string; properties: JsonSchemaProperty[] };

export type Preset = {
	id: string;
	kind: PresetKind;
	label: string;
	description: string | null;
	definition: Record<string, unknown>;
	version: number;
	builtin: boolean;
};

/**
 * Build a `field` preset definition from a schema field: the property, without its key,
 * archive state or any earlier provenance (saving a copy starts a new lineage).
 */
export function fieldToDefinition(field: EditorField): FieldDefinition {
	const prop = propertyFromField(field);
	const meta = { ...readPropMeta(prop) };
	delete meta.archived;
	delete meta.origin;
	return { property: replacePropMeta(prop, meta) };
}

/** Build a `choice_list` preset definition from a choice field's current options. */
export function optionsToDefinition(options: string[]): ChoiceListDefinition {
	return { options };
}

/** Build a `field_set` preset definition from a section: its label and its fields' properties. */
export function fieldSetToDefinition(
	sectionLabel: string,
	fields: EditorField[]
): FieldSetDefinition {
	return {
		section: sectionLabel,
		properties: fields.map((field) => fieldToDefinition(field).property)
	};
}

/**
 * Turn a saved `field` definition into a new, unsaved editor field, with fresh
 * provenance recorded. The key is resolved from the label when the schema is saved (WI-20).
 */
export function definitionToField(definition: FieldDefinition, origin: Origin): EditorField {
	const withOrigin = withPropMeta(definition.property, { origin });
	const field = fieldFromProperty('_pending', withOrigin, false);
	return { ...field, keyPending: true };
}

/**
 * Turn a saved `field_set` definition into a new, unsaved editor section: one pending
 * field per property, all sharing the same provenance. Keys are resolved from labels
 * when the schema is saved (WI-20), same as a single saved field.
 */
export function definitionToFieldSet(
	definition: FieldSetDefinition,
	origin: Origin,
	sectionId: string
): EditorSection {
	return {
		_section: true,
		id: sectionId,
		sectionLabel: definition.section,
		fields: definition.properties.map((property) => definitionToField({ property }, origin))
	};
}

/** Whether a choice field's stored list is out of date with the preset it came from. */
export function listUpdateAvailable(field: EditorField, preset: Preset | undefined): boolean {
	const origin = field.meta?.origin as Origin | undefined;
	return origin !== undefined && preset !== undefined && preset.version > origin.version;
}
