import { describe, it, expect } from 'vitest';
import { generateFieldKey, resolvePendingKeys } from '../src/lib/field-key';

describe('generateFieldKey', () => {
	const cases: [string, string][] = [
		['Director', 'director'],
		['My rating', 'my_rating'],
		['Signed?', 'signed'],
		['Track no.', 'track_no'],
		['Año de estreno', 'ano_de_estreno'],
		['Price (£)', 'price'],
		['監督, #', 'field'],
		['', 'field']
	];
	for (const [title, key] of cases) {
		it(`"${title}" becomes "${key}"`, () => {
			expect(generateFieldKey(title, [])).toBe(key);
		});
	}

	it('caps long titles at 40 characters without a trailing underscore', () => {
		const key = generateFieldKey('a'.repeat(39) + ' bbbbbb', []);
		expect(key.length).toBeLessThanOrEqual(40);
		expect(key.endsWith('_')).toBe(false);
	});

	it('appends _2, _3 when the key is taken, ignoring case', () => {
		expect(generateFieldKey('Director', ['director'])).toBe('director_2');
		expect(generateFieldKey('Director', ['DIRECTOR', 'director_2'])).toBe('director_3');
		expect(generateFieldKey('監督', ['field'])).toBe('field_2');
	});

	it('avoids names inherited from Object.prototype', () => {
		expect(generateFieldKey('Constructor', [])).toBe('constructor_2');
		expect(generateFieldKey('__proto__', [])).toBe('proto');
	});
});

type Item = { key: string; label: string; keyPending?: boolean };

describe('resolvePendingKeys', () => {
	const settled = (key: string, label = key): Item => ({ key, label });
	const pending = (label: string): Item => ({ key: 'placeholder', label, keyPending: true });

	it('derives keys for pending items and leaves settled keys alone', () => {
		const result = resolvePendingKeys([settled('director', 'Filmmaker'), pending('Year')]);
		expect(result.map((i) => i.key)).toEqual(['director', 'year']);
		expect(result[1].keyPending).toBe(false);
	});

	it('renaming a settled field label never changes its key', () => {
		const [field] = resolvePendingKeys([settled('director', 'Filmmaker')]);
		expect(field.key).toBe('director');
	});

	it('makes two pending fields with the same title unique', () => {
		const result = resolvePendingKeys([pending('Director'), pending('Director')]);
		expect(result.map((i) => i.key)).toEqual(['director', 'director_2']);
	});

	it('does not reuse the key of an existing (possibly archived) field', () => {
		const result = resolvePendingKeys([settled('director'), pending('Director')]);
		expect(result[1].key).toBe('director_2');
	});

	it('coexists with UUID keys', () => {
		const uuid = '3f0c6d1e-8f5b-4c0e-9a51-2b7d9d0f1a11';
		const result = resolvePendingKeys([settled(uuid, 'Legacy'), pending('Notes')]);
		expect(result.map((i) => i.key)).toEqual([uuid, 'notes']);
	});
});
