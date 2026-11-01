import { register } from '../registry';
import { readPropMeta } from '$lib/schema-meta';
import ListExtras from './ListExtras.svelte';
import ListInput from './ListInput.svelte';
import ListView from './ListView.svelte';

// Shape alone (a plain string array) is not distinctive enough to infer from - a future
// kind (e.g. multi-choice) could use the same shape - so this only matches an explicit kind.
// Order is preserved through JSONB for free (arrays keep position, unlike an object's keys),
// so unlike `group` this needs no explicit column-order bookkeeping in the metadata namespace.
register({
	kind: 'list',
	label: 'Ordered list',
	canBeSubField: false,
	displayOptions: [
		{
			key: 'display',
			label: 'Show as',
			choices: [
				{ value: 'numbered', label: 'Numbered' },
				{ value: 'bulleted', label: 'Bulleted' }
			],
			default: 'numbered'
		}
	],
	toSchema: (f) => ({ title: f.label, type: 'array', items: { type: 'string' } }),
	fromSchema: (key, prop, required) =>
		prop.type === 'array' && prop.items.type === 'string' && readPropMeta(prop).kind === 'list'
			? { key, label: prop.title, kind: 'list', required, options: [], subFields: [] }
			: null,
	EditorExtras: ListExtras,
	InputWidget: ListInput,
	ViewWidget: ListView
});
