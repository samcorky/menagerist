import { register } from '../registry';
import DateInput from './DateInput.svelte';
import DateView from './DateView.svelte';

register({
	kind: 'date',
	label: 'Date',
	canBeSubField: true,
	toSchema: (f) => ({ title: f.label, type: 'string', format: 'date' }),
	fromSchema: (key, prop, required) =>
		prop.type === 'string' && 'format' in prop && prop.format === 'date'
			? { key, label: prop.title, kind: 'date', required, options: [], subFields: [] }
			: null,
	InputWidget: DateInput,
	ViewWidget: DateView
});
