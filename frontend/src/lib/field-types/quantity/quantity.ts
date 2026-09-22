import { register } from '../registry';
import { readPropMeta } from '$lib/schema-meta';
import { quantityText } from './format';
import QuantityInput from './QuantityInput.svelte';
import QuantityView from './QuantityView.svelte';

// Shape alone (an object with `value`/`unit`) is not distinctive enough to infer from -
// a future kind could use the same shape - so this only matches an explicit kind.
// Not a group sub-field in v1: a group cell holds a plain string, not an object; making
// quantity nestable needs cell-level object values, which is its own follow-up.
register({
	kind: 'quantity',
	label: 'Quantity',
	canBeSubField: false,
	highlightable: true,
	formatSummary: (value) => {
		const text = quantityText(value);
		return text === '' ? null : text;
	},
	toSchema: (f) => ({
		title: f.label,
		type: 'object',
		properties: {
			value: { title: 'Value', type: 'number' },
			unit: { title: 'Unit', type: 'string' }
		}
	}),
	fromSchema: (key, prop, required) =>
		prop.type === 'object' && readPropMeta(prop).kind === 'quantity'
			? { key, label: prop.title, kind: 'quantity', required, options: [], subFields: [] }
			: null,
	InputWidget: QuantityInput,
	ViewWidget: QuantityView
});
