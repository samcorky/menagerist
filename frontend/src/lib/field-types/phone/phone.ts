import { register } from '../registry';
import ScalarInput from '../ScalarInput.svelte';
import PhoneView from './PhoneView.svelte';
import type { EditorField } from '$lib/schema-types';

// No native JSON Schema format for a phone number, so this is the same `pattern` variant `text`
// already uses (WI-15) - a permissive default pattern, distinguished from text only by shape
// (an exact match on this pattern) and by registration order (see index.ts).
export const PHONE_PATTERN = '^[0-9+()\\-\\s]{3,32}$';

register({
	kind: 'phone',
	label: 'Phone',
	canBeSubField: true,
	highlightable: true,
	toSchema: (f) => ({ title: f.label, type: 'string', pattern: PHONE_PATTERN }),
	fromSchema: (key, prop, required) => {
		if (prop.type !== 'string' || 'format' in prop || 'enum' in prop) return null;
		const p = prop as { pattern?: string; allOf?: unknown };
		if (p.pattern !== PHONE_PATTERN || p.allOf !== undefined) return null;
		const field: EditorField = {
			key,
			label: prop.title,
			kind: 'phone',
			required,
			options: [],
			subFields: []
		};
		return field;
	},
	InputWidget: ScalarInput,
	ViewWidget: PhoneView
});
