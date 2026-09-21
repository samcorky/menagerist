import { register } from '../registry';
import ChoiceInput from './ChoiceInput.svelte';
import ChoiceExtras from './ChoiceExtras.svelte';

register({
	kind: 'choice',
	label: 'Choice',
	canBeSubField: false,
	displayOptions: [
		{
			key: 'display',
			label: 'Show as',
			choices: [
				{ value: 'dropdown', label: 'Dropdown' },
				{ value: 'radio', label: 'Radio buttons' },
				{ value: 'chips', label: 'Chips' }
			],
			default: 'dropdown'
		}
	],
	toSchema: (f) => ({ title: f.label, type: 'string', enum: f.options }),
	fromSchema: (key, prop, required) => {
		if (prop.type !== 'string' || !('enum' in prop)) return null;
		return {
			key,
			label: prop.title,
			kind: 'choice',
			required,
			options: [...prop.enum],
			subFields: []
		};
	},
	EditorExtras: ChoiceExtras,
	InputWidget: ChoiceInput
});
