import { describe, it, expect } from 'vitest';
import { archiveField, restoreField } from '../src/lib/field-archive';
import type { EditorField } from '../src/lib/schema-types';

const field: EditorField = {
	key: 'year',
	label: 'Year',
	kind: 'number',
	required: false,
	options: [],
	subFields: [],
	meta: { kind: 'number', display: 'x', future: 1 }
};

describe('archiveField / restoreField', () => {
	it('archives without losing other metadata and does not mutate the input', () => {
		const archived = archiveField(field);
		expect(archived.meta).toEqual({ kind: 'number', display: 'x', future: 1, archived: true });
		expect(field.meta?.archived).toBeUndefined();
	});

	it('restore removes the flag and keeps the rest', () => {
		expect(restoreField(archiveField(field)).meta).toEqual(field.meta);
	});
});
