import { register } from '../registry';
import ScalarInput from '../ScalarInput.svelte';
import UrlView from './UrlView.svelte';

register({
	kind: 'url',
	label: 'URL',
	canBeSubField: true,
	highlightable: true,
	toSchema: (f) => ({ title: f.label, type: 'string', format: 'uri' }),
	fromSchema: (key, prop, required) =>
		prop.type === 'string' && 'format' in prop && prop.format === 'uri'
			? { key, label: prop.title, kind: 'url', required, options: [], subFields: [] }
			: null,
	InputWidget: ScalarInput,
	ViewWidget: UrlView
});
