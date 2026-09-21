import { register } from '../registry';
import BooleanInput from './BooleanInput.svelte';
import BooleanView from './BooleanView.svelte';
import BooleanSummary from './BooleanSummary.svelte';

register({
	kind: 'boolean',
	label: 'Yes/No',
	canBeSubField: true,
	highlightable: true,
	displayOptions: [
		{
			key: 'display',
			label: 'Show as',
			choices: [
				{ value: 'switch', label: 'Switch' },
				{ value: 'checkbox', label: 'Checkbox' },
				{ value: 'yes-no', label: 'Yes/No buttons' }
			],
			default: 'switch'
		}
	],
	toSchema: (f) => ({ title: f.label, type: 'boolean' }),
	fromSchema: (key, prop, required) =>
		prop.type === 'boolean'
			? { key, label: prop.title, kind: 'boolean', required, options: [], subFields: [] }
			: null,
	InputWidget: BooleanInput,
	ViewWidget: BooleanView,
	SummaryWidget: BooleanSummary
});
