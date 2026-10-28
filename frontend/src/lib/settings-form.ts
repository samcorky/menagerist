import type { SettingResponse } from '$lib/api/client';
import type { JsonSchemaProperty } from '$lib/json-schema';

/** A value a setting can hold: one scalar, or a list of strings. */
export type SettingValue = boolean | number | string | string[];

const GROUP_LABELS: Record<string, string> = {
	backup: 'Backups',
	scheduler: 'Scheduled tasks'
};

/** The heading for a group of settings. */
export function groupLabel(group: string): string {
	const label = GROUP_LABELS[group];
	if (label) return label;
	const words = group.replaceAll('_', ' ');
	return words.charAt(0).toUpperCase() + words.slice(1);
}

export type SettingGroup = { group: string; label: string; items: SettingResponse[] };

/** Settings grouped for display, in the order each group first appears. */
export function groupSettings(items: SettingResponse[]): SettingGroup[] {
	const groups = new Map<string, SettingGroup>();
	for (const item of items) {
		let entry = groups.get(item.group);
		if (!entry) {
			entry = { group: item.group, label: groupLabel(item.group), items: [] };
			groups.set(item.group, entry);
		}
		entry.items.push(item);
	}
	return [...groups.values()];
}

/**
 * The form's view of a setting's schema property. The API says `integer` where the form
 * widgets know `number`, so an integer becomes a number that must be a whole one.
 */
export function formProp(schemaProperty: unknown): JsonSchemaProperty {
	const prop = { ...(schemaProperty as Record<string, unknown>) };
	if (prop.type === 'integer') {
		prop.type = 'number';
		prop.multipleOf = 1;
	}
	return prop as unknown as JsonSchemaProperty;
}

/** The properties of the settings schema document, by setting key. */
export function schemaProperties(schema: unknown): Record<string, unknown> {
	if (typeof schema === 'object' && schema !== null && 'properties' in schema) {
		const props = (schema as { properties: unknown }).properties;
		if (typeof props === 'object' && props !== null) return props as Record<string, unknown>;
	}
	return {};
}

/** Where a value came from, in the words the page uses. */
export function sourceLabel(item: Pick<SettingResponse, 'source'>): string {
	switch (item.source) {
		case 'env':
			return 'Set by your deployment';
		case 'instance':
		case 'user':
			return 'Changed here';
		default:
			return 'Default';
	}
}

/** Why a setting cannot be changed here, or null when it can. */
export function lockedNote(item: Pick<SettingResponse, 'locked' | 'env_name'>): string | null {
	if (!item.locked) return null;
	const where = item.env_name ? ` (${item.env_name})` : '';
	return `Your deployment sets this${where}. Remove it there to change it here.`;
}

/** A reminder that a change needs a restart, or null. */
export function restartNote(item: Pick<SettingResponse, 'restart_required'>): string | null {
	return item.restart_required ? 'A change takes effect after a restart.' : null;
}

/** A saved value that no longer passes the setting's rules is ignored; say so. */
export function staleNote(item: Pick<SettingResponse, 'stored_invalid'>): string | null {
	return item.stored_invalid
		? 'The saved value is no longer valid, so the default is in use. Save a new value to replace it.'
		: null;
}

export type Coerced = { ok: true; value: SettingValue } | { ok: false; message: string };

/**
 * Turn what a widget holds into the value to save, or say what is wrong with it.
 * Number inputs hand over text; a schedule is trimmed, and an empty one means off.
 */
export function coerce(prop: JsonSchemaProperty, raw: unknown): Coerced {
	if (prop.type === 'number') {
		if (typeof raw === 'number' && Number.isFinite(raw)) return check(prop, raw);
		const text = typeof raw === 'string' ? raw.trim() : '';
		if (text === '') return { ok: false, message: 'Enter a number.' };
		const value = Number(text);
		if (!Number.isFinite(value)) return { ok: false, message: 'Enter a number.' };
		return check(prop, value);
	}
	if (prop.type === 'string') {
		return typeof raw === 'string'
			? { ok: true, value: raw.trim() }
			: { ok: false, message: 'Enter some text.' };
	}
	if (prop.type === 'boolean') {
		return typeof raw === 'boolean'
			? { ok: true, value: raw }
			: { ok: false, message: 'Choose yes or no.' };
	}
	if (Array.isArray(raw) && raw.every((item) => typeof item === 'string')) {
		return { ok: true, value: raw as string[] };
	}
	return { ok: false, message: 'This value is not valid.' };
}

function check(prop: JsonSchemaProperty & { type: 'number' }, value: number): Coerced {
	if (prop.multipleOf === 1 && !Number.isInteger(value)) {
		return { ok: false, message: 'Use a whole number.' };
	}
	if (prop.minimum !== undefined && value < prop.minimum) {
		return { ok: false, message: `Must be at least ${prop.minimum}.` };
	}
	if (prop.maximum !== undefined && value > prop.maximum) {
		return { ok: false, message: `Must be at most ${prop.maximum}.` };
	}
	return { ok: true, value };
}

/** Whether a draft differs from the setting's current value once coerced. */
export function isChanged(
	prop: JsonSchemaProperty,
	current: SettingValue,
	draft: unknown
): boolean {
	const coerced = coerce(prop, draft);
	if (!coerced.ok) return true;
	return JSON.stringify(coerced.value) !== JSON.stringify(current);
}

/** The body of an update that changes one setting. */
export function updateBody(
	key: string,
	value: SettingValue
): { values: Record<string, SettingValue> } {
	return { values: { [key]: value } };
}
