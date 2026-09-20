import { register } from './registry';
import BooleanInput from './BooleanInput.svelte';

register({
	kind: 'boolean',
	label: 'Yes/No',
	canBeSubField: true,
	toSchema: (f) => ({ title: f.label, type: 'boolean' }),
	fromSchema: (key, prop, required) =>
		prop.type === 'boolean'
			? { key, label: prop.title, kind: 'boolean', required, options: [], subFields: [] }
			: null,
	InputWidget: BooleanInput
});
