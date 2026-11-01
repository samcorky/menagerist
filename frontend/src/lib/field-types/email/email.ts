import { register } from '../registry';
import ScalarInput from '../ScalarInput.svelte';
import EmailView from './EmailView.svelte';

register({
	kind: 'email',
	label: 'Email',
	canBeSubField: true,
	highlightable: true,
	toSchema: (f) => ({ title: f.label, type: 'string', format: 'email' }),
	fromSchema: (key, prop, required) =>
		prop.type === 'string' && 'format' in prop && prop.format === 'email'
			? { key, label: prop.title, kind: 'email', required, options: [], subFields: [] }
			: null,
	InputWidget: ScalarInput,
	ViewWidget: EmailView
});
