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
	// A saved field stands alone: a linked field's options are copied in, not referenced.
	const linked = meta.list !== undefined;
	delete meta.list;
	const copied = linked ? { ...prop, enum: [...field.options] } : prop;
	return { property: replacePropMeta(copied, meta) };
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

/** The options a `choice_list` preset holds. */
export function listOptions(preset: Preset): string[] {
	return (preset.definition as { options: string[] }).options;
}

/** The saved list a choice field is linked to, or undefined for a copy. */
export function linkedListId(field: EditorField): string | undefined {
	return field.meta?.list;
}

/** Link a choice field to a saved list: its options become the list's, and any copy origin is dropped. */
export function linkToList(field: EditorField, preset: Preset): EditorField {
	const { origin: _origin, ...meta } = field.meta ?? {};
	return { ...field, options: listOptions(preset), meta: { ...meta, list: preset.id } };
}

/** Turn a linked choice field into an ordinary copy, keeping its current options. */
export function unlinkField(field: EditorField): EditorField {
	const { list: _list, ...meta } = field.meta ?? {};
	return { ...field, meta };
}

/**
 * Whether a choice field's stored list is out of date with the preset it came from.
 * Linked fields always see the current list, so they never report an update.
 */
export function listUpdateAvailable(field: EditorField, preset: Preset | undefined): boolean {
	if (linkedListId(field) !== undefined) return false;
	const origin = field.meta?.origin as Origin | undefined;
	return origin !== undefined && preset !== undefined && preset.version > origin.version;
}
