import { register } from '../registry';
import PartialDateInput from './PartialDateInput.svelte';
import PartialDateView from './PartialDateView.svelte';
import { formatPartialDate } from '$lib/format-date';
import type { EditorField } from '$lib/schema-types';

// `YYYY`, `YYYY-MM` or `YYYY-MM-DD`. The pattern checks ranges (month 01-12, day 01-31) but not
// month lengths, so 1973-02-30 is accepted. Like `phone`, it is a `pattern` string told apart
// from `text` by an exact match on the pattern, and registered before `text` (see index.ts).
export const PARTIAL_DATE_PATTERN = '^[0-9]{4}(-(0[1-9]|1[0-2])(-(0[1-9]|[12][0-9]|3[01]))?)?$';

register({
	kind: 'partialdate',
	label: 'Partial date',
	canBeSubField: true,
	highlightable: true,
	toSchema: (f) => ({ title: f.label, type: 'string', pattern: PARTIAL_DATE_PATTERN }),
	fromSchema: (key, prop, required) => {
		if (prop.type !== 'string' || 'format' in prop || 'enum' in prop) return null;
		const p = prop as { pattern?: string; allOf?: unknown };
		if (p.pattern !== PARTIAL_DATE_PATTERN || p.allOf !== undefined) return null;
		const field: EditorField = {
			key,
			label: prop.title,
			kind: 'partialdate',
			required,
			options: [],
			subFields: []
		};
		return field;
	},
	formatError: (keyword) =>
		keyword === 'pattern'
			? 'Enter a year, a year and month, or a full date: 1973, 1973-03 or 1973-03-14.'
			: null,
	formatSummary: (value) => (typeof value === 'string' ? formatPartialDate(value, 'short') : null),
	InputWidget: PartialDateInput,
	ViewWidget: PartialDateView
});
