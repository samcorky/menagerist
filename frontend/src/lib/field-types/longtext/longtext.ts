import { register } from '../registry';
import { readPropMeta } from '$lib/schema-meta';
import LongtextInput from './LongtextInput.svelte';

register({
	kind: 'longtext',
	label: 'Long text',
	canBeSubField: true,
	toSchema: (f) => ({ title: f.label, type: 'string' }),
	// Shape alone cannot tell longtext from text, so it only matches an explicit kind.
	fromSchema: (key, prop, required) =>
		prop.type === 'string' && readPropMeta(prop).kind === 'longtext' && !('enum' in prop)
			? { key, label: prop.title, kind: 'longtext', required, options: [], subFields: [] }
			: null,
	InputWidget: LongtextInput
});
