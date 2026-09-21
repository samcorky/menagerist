import { register } from '../registry';
import ScalarInput from '../ScalarInput.svelte';
import TextExtras from './TextExtras.svelte';
import {
	constraintKeywords,
	describePattern,
	parseConstraints,
	readTextConfig
} from './constraints';
import type { EditorField, JsonSchemaProperty } from '$lib/schema-types';

register({
	kind: 'text',
	label: 'Text',
	canBeSubField: true,
	toSchema: (f) => {
		const { startsWith, endsWith, custom } = readTextConfig(f);
		return {
			title: f.label,
			type: 'string',
			...(custom ?? constraintKeywords({ startsWith, endsWith }))
		} as JsonSchemaProperty;
	},
	fromSchema: (key, prop, required) => {
		if (prop.type !== 'string' || 'format' in prop || 'enum' in prop) return null;
		const { constraints, custom } = parseConstraints(prop);
		const field: EditorField = {
			key,
			label: prop.title,
			kind: 'text',
			required,
			options: [],
			subFields: []
		};
		if (custom) field.config = { custom };
		else if (constraints.startsWith || constraints.endsWith) field.config = { ...constraints };
		return field;
	},
	formatError: (keyword, value) => (keyword === 'pattern' ? describePattern(value) : null),
	EditorExtras: TextExtras,
	InputWidget: ScalarInput
});
