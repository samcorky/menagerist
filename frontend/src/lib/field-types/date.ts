import { register } from './registry';
import ScalarInput from './ScalarInput.svelte';

register({
	kind: 'date',
	label: 'Date',
	canBeSubField: true,
	toSchema: (f) => ({ title: f.label, type: 'string', format: 'date' }),
	fromSchema: (key, prop, required) =>
		prop.type === 'string' && 'format' in prop && prop.format === 'date'
			? { key, label: prop.title, kind: 'date', required, options: [], subFields: [] }
			: null,
	InputWidget: ScalarInput
});
