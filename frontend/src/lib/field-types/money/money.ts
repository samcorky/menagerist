import { register } from '../registry';
import { readPropMeta } from '$lib/schema-meta';
import { moneyText } from './format';
import MoneyInput from './MoneyInput.svelte';
import MoneyView from './MoneyView.svelte';

// Shape alone (an object with `value`/`currency`) is not distinctive enough to infer from -
// matches quantity's own precedent - so this only matches an explicit kind.
register({
	kind: 'money',
	label: 'Money',
	canBeSubField: true,
	highlightable: true,
	formatSummary: (value) => {
		const text = moneyText(value);
		return text === '' ? null : text;
	},
	toSchema: (f) => ({
		title: f.label,
		type: 'object',
		properties: {
			value: { title: 'Value', type: 'number' },
			currency: { title: 'Currency', type: 'string' }
		}
	}),
	fromSchema: (key, prop, required) =>
		prop.type === 'object' && readPropMeta(prop).kind === 'money'
			? { key, label: prop.title, kind: 'money', required, options: [], subFields: [] }
			: null,
	InputWidget: MoneyInput,
	ViewWidget: MoneyView
});
