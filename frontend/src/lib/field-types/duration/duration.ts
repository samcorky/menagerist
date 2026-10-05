import { register } from '../registry';
import { readPropMeta } from '$lib/schema-meta';
import DurationInput from './DurationInput.svelte';
import DurationView from './DurationView.svelte';
import { durationSeconds, formatDuration, type DurationStyle } from './format';

// Shape alone cannot tell a duration from a number, so it only matches an explicit kind.
// Stored as whole seconds, so values sort and add up.
register({
	kind: 'duration',
	label: 'Duration',
	canBeSubField: true,
	highlightable: true,
	displayOptions: [
		{
			key: 'display',
			label: 'Show as',
			choices: [
				{ value: 'clock', label: '1:02:03' },
				{ value: 'words', label: '1h 2m 3s' }
			],
			default: 'clock'
		}
	],
	toSchema: (f) => ({ title: f.label, type: 'number', minimum: 0, multipleOf: 1 }),
	fromSchema: (key, prop, required) =>
		prop.type === 'number' && readPropMeta(prop).kind === 'duration'
			? { key, label: prop.title, kind: 'duration', required, options: [], subFields: [] }
			: null,
	formatError: (keyword) =>
		keyword === 'type' || keyword === 'minimum' || keyword === 'multipleOf'
			? 'Enter a duration such as 3:45, 1:02:03 or 1h 2m 3s.'
			: null,
	formatSummary: (value, prop) => {
		const seconds = durationSeconds(value);
		return seconds === null
			? null
			: formatDuration(seconds, (readPropMeta(prop).display as DurationStyle) ?? 'clock');
	},
	InputWidget: DurationInput,
	ViewWidget: DurationView
});
