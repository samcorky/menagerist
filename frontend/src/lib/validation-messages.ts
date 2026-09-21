import { descriptorForProp } from '$lib/field-types';
import type { AttributesSchema, JsonSchemaProperty } from '$lib/schema-types';

type Node = Record<string, unknown>;

function isNode(value: unknown): value is Node {
	return typeof value === 'object' && value !== null;
}

function decode(segment: string): string {
	let text = segment;
	try {
		text = decodeURIComponent(segment);
	} catch {
		// keep the raw segment
	}
	return text.replace(/~1/g, '/').replace(/~0/g, '~');
}

/** The nearest typed property above a validator's keyword location, and the keyword's value. */
function locate(
	schema: AttributesSchema,
	keywordLocation: string
): { prop: JsonSchemaProperty | undefined; value: unknown } {
	let current: unknown = schema;
	let prop: JsonSchemaProperty | undefined;
	for (const raw of keywordLocation.replace(/^#\/?/, '').split('/')) {
		if (!isNode(current) && !Array.isArray(current)) break;
		current = (current as Node)[decode(raw)];
		if (isNode(current) && !Array.isArray(current) && 'type' in current) {
			prop = current as unknown as JsonSchemaProperty;
		}
	}
	return { prop, value: current };
}

/** Friendly message for a client-side validator error. */
export function friendlyClientError(
	schema: AttributesSchema,
	error: { keyword: string; keywordLocation: string; error: string }
): string {
	const { prop, value } = locate(schema, error.keywordLocation);
	const friendly = prop && descriptorForProp(prop)?.formatError?.(error.keyword, value);
	return friendly || error.error || 'Invalid value';
}

/** Property at a JSON Pointer such as `/cover_file` or `/tracks/0/code`. */
function propAtPath(schema: AttributesSchema, path: string): JsonSchemaProperty | undefined {
	let current: Node = schema as unknown as Node;
	for (const raw of path.split('/').filter((s) => s !== '')) {
		const segment = decode(raw);
		const props = current.properties;
		if (isNode(props) && Object.hasOwn(props, segment)) current = props[segment] as Node;
		else if (/^\d+$/.test(segment) && isNode(current.items)) current = current.items as Node;
		else return undefined;
	}
	return current as unknown as JsonSchemaProperty;
}

/** Friendly message for a server validation error (`path`, `keyword`, `value`, `message`). */
export function friendlyServerError(
	schema: AttributesSchema | null,
	error: { path?: string; message?: string; keyword?: string; value?: unknown }
): string {
	const prop = schema && error.path ? propAtPath(schema, error.path) : undefined;
	const friendly =
		prop && error.keyword
			? descriptorForProp(prop)?.formatError?.(error.keyword, error.value)
			: null;
	return friendly || error.message || 'Invalid value';
}

/** The top-level attribute key of an instance location such as `#/tracks/0/code` or `/tracks`. */
export function topLevelKey(location: string): string {
	return decode(location.replace(/^#?\/?/, '').split('/')[0] ?? '');
}

/**
 * Map server validation errors onto top-level fields (an error inside a table row is shown on
 * the table). The first error per field wins.
 */
export function serverErrorsToFields(
	schema: AttributesSchema | null,
	errors: { path?: string; message?: string; keyword?: string; value?: unknown }[]
): Record<string, string> {
	const out: Record<string, string> = {};
	for (const e of errors) {
		if (!e.path || e.path === '/') continue;
		const key = topLevelKey(e.path);
		if (key && !(key in out)) out[key] = friendlyServerError(schema, e);
	}
	return out;
}
