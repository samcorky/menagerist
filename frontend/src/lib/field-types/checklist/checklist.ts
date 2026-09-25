import { register } from '../registry';
import { readPropMeta } from '$lib/schema-meta';
import { checklistCount } from './format';
import ChecklistInput from './ChecklistInput.svelte';
import ChecklistView from './ChecklistView.svelte';

// Stored as an array of {text, done} rows, not a plain string array like `list` - each item
// needs its own persisted tick, which is real data, not just a rendering style. Shape alone
// (an array of objects) is not distinctive enough to infer from - the same shape a `group`
// column could use - so this only matches an explicit kind, same reasoning as `list`/`quantity`.
register({
	kind: 'checklist',
	label: 'Checklist',
	canBeSubField: false,
	highlightable: true,
	formatSummary: (value) => {
		const count = checklistCount(value);
		return count ? `${count.checked}/${count.total}` : null;
	},
	toSchema: (f) => ({
		title: f.label,
		type: 'array',
		items: {
			type: 'object',
			properties: {
				text: { title: 'Text', type: 'string' },
				done: { title: 'Done', type: 'boolean' }
			}
		}
	}),
	fromSchema: (key, prop, required) =>
		prop.type === 'array' && prop.items.type === 'object' && readPropMeta(prop).kind === 'checklist'
			? { key, label: prop.title, kind: 'checklist', required, options: [], subFields: [] }
			: null,
	InputWidget: ChecklistInput,
	ViewWidget: ChecklistView
});
