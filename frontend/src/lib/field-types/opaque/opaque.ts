import { register } from '../registry';
import ScalarInput from '../ScalarInput.svelte';
import type { JsonSchemaProperty } from '$lib/schema-types';

/** Holds a property no other descriptor recognises so it survives open-edit-save unchanged. */
register({
	kind: 'opaque',
	label: 'Custom',
	canBeSubField: true,
	selectable: false,
	toSchema: (f) => ({ ...f.raw, title: f.label }) as JsonSchemaProperty,
	fromSchema: () => null,
	InputWidget: ScalarInput
});
