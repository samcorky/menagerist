import { register } from '../registry';
import MultiChoiceExtras from './MultiChoiceExtras.svelte';
import MultiChoiceInput from './MultiChoiceInput.svelte';
import MultiChoiceView from './MultiChoiceView.svelte';

// The `items.enum` shape is distinctive (`list` needs an explicit kind and `group` needs
// object items), so this also matches an API-authored property with no `kind`.
register({
	kind: 'multichoice',
	label: 'Multiple choice',
	canBeSubField: false,
	highlightable: true,
	displayOptions: [
		{
			key: 'display',
			label: 'Show as',
			choices: [
				{ value: 'chips', label: 'Chips' },
				{ value: 'checkboxes', label: 'Checkboxes' }
			],
			default: 'chips'
		}
	],
	formatSummary: (value) =>
		Array.isArray(value) && value.length > 0 ? value.map(String).join(', ') : null,
	toSchema: (f) => ({
		title: f.label,
		type: 'array',
		items: { type: 'string', enum: f.options },
		uniqueItems: true
	}),
	fromSchema: (key, prop, required) =>
		prop.type === 'array' && prop.items?.type === 'string' && prop.items.enum !== undefined
			? {
					key,
					label: prop.title,
					kind: 'multichoice',
					required,
					options: [...(prop.items.enum ?? [])],
					subFields: []
				}
			: null,
	EditorExtras: MultiChoiceExtras,
	InputWidget: MultiChoiceInput,
	ViewWidget: MultiChoiceView
});
