import type { EditorField } from '$lib/schema-types';
import type { DisplayOption } from './registry';

/** Current value of a display option for a field (its default when unset). */
export function displayValue(field: EditorField, option: DisplayOption): string {
	const stored = option.key === 'display' ? field.meta?.display : field.config?.[option.key];
	return typeof stored === 'string' || typeof stored === 'number' ? String(stored) : option.default;
}

/** Choices for a display option, including a stored value the descriptor does not list. */
export function displayChoices(
	field: EditorField,
	option: DisplayOption
): { value: string; label: string }[] {
	const current = displayValue(field, option);
	return option.choices.some((c) => c.value === current)
		? option.choices
		: [...option.choices, { value: current, label: current }];
}

/** Return the field with a display option changed. The default is stored as "unset". */
export function setDisplayValue(
	field: EditorField,
	option: DisplayOption,
	value: string
): EditorField {
	if (option.key === 'display') {
		const meta = { ...field.meta };
		if (value === option.default) delete meta.display;
		else meta.display = value;
		return { ...field, meta };
	}
	return { ...field, config: { ...field.config, [option.key]: value } };
}
