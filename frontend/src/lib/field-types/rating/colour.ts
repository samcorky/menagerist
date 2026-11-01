import { readPropMeta } from '$lib/schema-meta';
import type { JsonSchemaProperty } from '$lib/schema-types';

/** Filled-star classes for a rating field's chosen colour display option (default amber). */
export function filledStarClass(prop: JsonSchemaProperty): string {
	return readPropMeta(prop).display === 'accent'
		? 'fill-primary text-primary'
		: 'fill-amber-400 text-amber-400';
}
