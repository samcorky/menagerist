import { register } from './registry';
import ScalarInput from './ScalarInput.svelte';

register({
	kind: 'number',
	label: 'Number',
	canBeSubField: true,
	toSchema: (f) => ({ title: f.label, type: 'number' }),
	fromSchema: (key, prop, required) =>
		prop.type === 'number'
			? { key, label: prop.title, kind: 'number', required, options: [], subFields: [] }
			: null,
	InputWidget: ScalarInput
});
