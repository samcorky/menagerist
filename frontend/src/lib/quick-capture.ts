/** Which of an item type's fields quick capture asks for. */
import { QUICK_CAPTURE_KINDS } from '$lib/field-flags';
import { isSection, schemaToItems } from '$lib/schema-editor-items';
import type { AttributesSchema } from '$lib/schema-types';

/** Keys of the type's fields flagged for quick capture, in the order the type shows them. */
export function captureFieldKeys(schema: AttributesSchema | null): string[] {
	return schemaToItems(schema)
		.flatMap((item) => (isSection(item) ? item.fields : [item]))
		.filter(
			(field) =>
				field.meta?.capture === true && !field.meta.archived && QUICK_CAPTURE_KINDS.has(field.kind)
		)
		.map((field) => field.key);
}
