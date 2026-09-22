import type { AttributesSchema, JsonSchemaProperty } from '$lib/schema-types';

export type GroupRow = Record<string, string>;

/** How a detail that the type's fields do not define is edited and stored. */
export type DetailKind = 'text' | 'number' | 'boolean' | 'json';

export type AttributeRow = {
	key: string;
	value: string | GroupRow[] | GroupRow;
	/** Type of a detail without a field; text when unset. Ignored for fields the type defines. */
	kind?: DetailKind;
	/** The stored value of a detail the form cannot edit; written back unchanged. */
	raw?: unknown;
	/** Set on rows added with "Add detail", so they stay details even if the name matches a field. */
	extra?: boolean;
};

function isGroupValue(value: unknown): value is Record<string, unknown>[] {
	return (
		Array.isArray(value) &&
		value.every((v) => typeof v === 'object' && v !== null && !Array.isArray(v))
	);
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
	return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function compareKeys(a: string, b: string): number {
	const lower = a.toLowerCase().localeCompare(b.toLowerCase());
	return lower !== 0 ? lower : a.localeCompare(b);
}

/**
 * Convert an API `attributes` dict into editable rows, ordered by name (case-insensitively):
 * the database does not keep key order, so this is the only stable order.
 * Numbers and yes/no values keep their type; a value under a key the schema defines as
 * `type: 'object'` (for example a quantity's `{value, unit}`) is edited as a flat, stringified
 * row. Anything else the form cannot edit (null, nested values, other objects) keeps its
 * original value in `raw`.
 */
export function attributesToRows(
	attributes: Record<string, unknown>,
	schema?: AttributesSchema | null
): AttributeRow[] {
	const props = schema?.properties ?? {};
	return Object.entries(attributes)
		.sort(([a], [b]) => compareKeys(a, b))
		.map(([key, value]): AttributeRow => {
			if (isGroupValue(value)) {
				return {
					key,
					value: value.map((entry) =>
						Object.fromEntries(Object.entries(entry).map(([k, v]) => [k, String(v)]))
					),
					kind: 'json',
					raw: value
				};
			}
			if (props[key]?.type === 'object' && isPlainObject(value)) {
				return {
					key,
					value: Object.fromEntries(Object.entries(value).map(([k, v]) => [k, String(v)]))
				};
			}
			if (typeof value === 'string') return { key, value };
			if (typeof value === 'number') return { key, value: String(value), kind: 'number' };
			if (typeof value === 'boolean') return { key, value: String(value), kind: 'boolean' };
			return { key, value: JSON.stringify(value) ?? '', kind: 'json', raw: value };
		});
}

/** A new, empty row for "Add detail". */
export function newDetailRow(kind: DetailKind = 'text'): AttributeRow {
	return { key: '', value: kind === 'boolean' ? 'false' : '', kind, extra: true };
}

function isOmittedWhenEmpty(prop: JsonSchemaProperty | undefined): boolean {
	if (!prop) return false;
	if (prop.type === 'number') return true;
	if (prop.type !== 'string') return false;
	// An empty string fails an anchored pattern, so an empty constrained text field is omitted.
	const p = prop as { pattern?: unknown; allOf?: unknown };
	return (
		'enum' in prop ||
		('format' in prop && prop.format === 'date') ||
		p.pattern !== undefined ||
		p.allOf !== undefined
	);
}

function coerceScalar(value: string, prop: JsonSchemaProperty | undefined): unknown {
	if (prop?.type === 'number') {
		const n = Number(value);
		return isNaN(n) ? value : n;
	}
	// An untouched checkbox has no unset state, so '' becomes false.
	if (prop?.type === 'boolean') return value === 'true';
	return value;
}

/** Write a detail (a key the schema does not define) back with its own type. */
function detailEntry(key: string, row: AttributeRow): [string, unknown][] {
	if (row.raw !== undefined && (row.kind === 'json' || typeof row.value !== 'string')) {
		return [[key, row.raw]];
	}
	// A composite value with no defining schema (e.g. the type field was removed) has no
	// `raw` to fall back to; write it back as-is rather than losing the sub-values.
	if (typeof row.value !== 'string') return [[key, row.value]];
	if (row.kind === 'number') {
		if (row.value === '') return [];
		const n = Number(row.value);
		return [[key, isNaN(n) ? row.value : n]];
	}
	if (row.kind === 'boolean') return row.value === '' ? [] : [[key, row.value === 'true']];
	return [[key, row.value]];
}

/**
 * Convert edited rows into a typed `attributes` dict ready for the API.
 * Pass `schema` so number/boolean fields are emitted as real JS types.
 * Empty number, date and enum values are omitted rather than sent as empty strings.
 * Names are trimmed; details keep their own type and unchanged values are written back as stored.
 */
export function rowsToAttributes(
	rows: AttributeRow[],
	schema?: AttributesSchema | null
): Record<string, unknown> {
	const props = schema?.properties ?? {};
	return Object.fromEntries(
		rows
			.filter((row) => row.key.trim() !== '')
			.flatMap((row): [string, unknown][] => {
				const key = row.key.trim();
				const prop = Object.hasOwn(props, key) ? props[key] : undefined;
				if (!prop) return detailEntry(key, row);
				if (typeof row.value !== 'string') {
					if (prop.type === 'array' && prop.items?.type === 'object' && Array.isArray(row.value)) {
						const subProps = prop.items.properties ?? {};
						return [
							[
								key,
								row.value.map((gr) =>
									Object.fromEntries(
										Object.entries(gr)
											.filter(([k, v]) => !(v === '' && isOmittedWhenEmpty(subProps[k])))
											.map(([k, v]) => [k, coerceScalar(v, subProps[k])])
									)
								)
							]
						];
					}
					if (prop.type === 'object' && !Array.isArray(row.value)) {
						// Nothing entered at all omits the whole field, checked on the raw values
						// (not the filtered ones below) so a blank text sub-value like a unit -
						// kept deliberately, same as a group's text cells - doesn't count as "filled".
						if (Object.values(row.value).every((v) => v === '')) return [];
						const subProps = prop.properties ?? {};
						const entries = Object.entries(row.value)
							.filter(([k, v]) => !(v === '' && isOmittedWhenEmpty(subProps[k])))
							.map(([k, v]) => [k, coerceScalar(v, subProps[k])]);
						return [[key, Object.fromEntries(entries)]];
					}
					return [[key, row.value]];
				}
				if (row.value === '' && isOmittedWhenEmpty(prop)) return [];
				if (prop.type === 'number') {
					if (row.value === '') return [];
					const n = Number(row.value);
					return isNaN(n) ? [[key, row.value]] : [[key, n]];
				}
				// An empty top-level boolean means "not recorded", not false.
				if (prop.type === 'boolean' && row.value === '') return [];
				if (prop.type === 'boolean') return [[key, row.value === 'true']];
				return [[key, row.value]];
			})
	);
}
