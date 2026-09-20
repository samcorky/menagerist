import { register } from '../registry';
import LongtextInput from './LongtextInput.svelte';

register({
	kind: 'longtext',
	label: 'Long text',
	canBeSubField: true,
	toSchema: (f) => ({ title: f.label, type: 'string', 'x-multiline': true }),
	fromSchema: (key, prop, required) =>
		prop.type === 'string' && 'x-multiline' in prop && prop['x-multiline'] === true
			? { key, label: prop.title, kind: 'longtext', required, options: [], subFields: [] }
			: null,
	InputWidget: LongtextInput
});
