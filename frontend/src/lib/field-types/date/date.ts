import { register } from '../registry';
import DateInput from './DateInput.svelte';
import DateView from './DateView.svelte';
import { formatIsoDate } from '$lib/format-date';

register({
	kind: 'date',
	label: 'Date',
	canBeSubField: true,
	highlightable: true,
	toSchema: (f) => ({ title: f.label, type: 'string', format: 'date' }),
	fromSchema: (key, prop, required) =>
		prop.type === 'string' && 'format' in prop && prop.format === 'date'
			? { key, label: prop.title, kind: 'date', required, options: [], subFields: [] }
			: null,
	InputWidget: DateInput,
	formatSummary: (value) => (typeof value === 'string' ? formatIsoDate(value, 'short') : null),
	ViewWidget: DateView
});
