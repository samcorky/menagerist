import { register } from '../registry';
import ScalarInput from '../ScalarInput.svelte';

register({
	kind: 'text',
	label: 'Text',
	canBeSubField: true,
	toSchema: (f) => ({ title: f.label, type: 'string' }),
	fromSchema: (key, prop, required) => {
		if (prop.type !== 'string' || 'format' in prop || 'enum' in prop) return null;
		return { key, label: prop.title, kind: 'text', required, options: [], subFields: [] };
	},
	InputWidget: ScalarInput
});
