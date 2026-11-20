import type { JsonSchemaProperty } from '$lib/json-schema';
import { regionFirstDay } from '$lib/calendar-settings';
import { currentPrefs, formatIsoDate, formatTime, weekdayName } from '$lib/format-date';
import { readPropMeta, withPropMeta } from '$lib/prop-meta';

/**
 * What an "Automatic" choice comes to on this device, worked out here because only the browser
 * knows its language and region: "Monday", "20 Nov 2026", "14:30". Each setting's description
 * says where Automatic comes from.
 */
export function automaticExample(
	key: string,
	now: Date = new Date(),
	locale: string = typeof navigator === 'undefined' ? 'en-GB' : navigator.language
): string | null {
	switch (key) {
		case 'datetime.first_day':
			return weekdayName(regionFirstDay(locale), locale);
		case 'datetime.date_order': {
			const pad = (n: number) => String(n).padStart(2, '0');
			const today = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
			const example = formatIsoDate(today, 'short', {
				...currentPrefs(),
				order: 'automatic',
				locale
			});
			return example;
		}
		case 'datetime.clock':
			return formatTime(now, { ...currentPrefs(), clock: 'automatic', locale });
		default:
			return null;
	}
}

/** The setting's schema with its "automatic" option labelled by what it comes to here. */
export function withAutomaticExample(key: string, prop: JsonSchemaProperty): JsonSchemaProperty {
	const labels = readPropMeta(prop).labels;
	const example = automaticExample(key);
	if (!labels || !('automatic' in labels) || example === null) return prop;
	return withPropMeta(prop, { labels: { ...labels, automatic: `Automatic (${example})` } });
}
