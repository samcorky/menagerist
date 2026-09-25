import { describe, it, expect } from 'vitest';
import { Validator } from '@cfworker/json-schema';
import { attributesToRows, rowsToAttributes, type AttributeRow } from '../src/lib/attribute-rows';
import type { AttributesSchema } from '../src/lib/schema-types';

const schema = (properties: AttributesSchema['properties']): AttributesSchema => ({
	$schema: 'https://json-schema.org/draft/2020-12/schema',
	type: 'object',
	properties
});

describe('attributesToRows', () => {
	it('converts scalar attributes to string-valued rows in name order, keeping number and yes/no types', () => {
		expect(attributesToRows({ colour: 'red', count: 3, active: true })).toEqual([
			{ key: 'active', value: 'true', kind: 'boolean' },
			{ key: 'colour', value: 'red' },
			{ key: 'count', value: '3', kind: 'number' }
		]);
	});

	it('converts a repeating group into a row with an array of stringified sub-rows', () => {
		const rows = attributesToRows({
			ingredients: [
				{ name: 'Flour', quantity: 200, unit: 'g' },
				{ name: 'Sugar', quantity: 50, unit: 'g' }
			]
		});

		expect(rows).toEqual([
			{
				key: 'ingredients',
				value: [
					{ name: 'Flour', quantity: '200', unit: 'g' },
					{ name: 'Sugar', quantity: '50', unit: 'g' }
				],
				kind: 'json',
				raw: [
					{ name: 'Flour', quantity: 200, unit: 'g' },
					{ name: 'Sugar', quantity: 50, unit: 'g' }
				]
			}
		]);
	});

	it('treats an empty group as an empty array of rows, not a scalar', () => {
		expect(attributesToRows({ ingredients: [] })).toEqual([
			{ key: 'ingredients', value: [], kind: 'json', raw: [] }
		]);
	});
});

describe('rowsToAttributes', () => {
	it('drops rows with an empty or whitespace key', () => {
		const rows: AttributeRow[] = [
			{ key: 'colour', value: 'red' },
			{ key: '', value: 'ignored' },
			{ key: '   ', value: 'ignored' }
		];

		expect(rowsToAttributes(rows)).toEqual({ colour: 'red' });
	});

	it('passes group rows through as an array of records', () => {
		const rows: AttributeRow[] = [
			{
				key: 'ingredients',
				value: [{ name: 'Flour', quantity: '200', unit: 'g' }]
			}
		];

		expect(rowsToAttributes(rows)).toEqual({
			ingredients: [{ name: 'Flour', quantity: '200', unit: 'g' }]
		});
	});
});

describe('round-trip', () => {
	it('preserves a repeating group through attributesToRows then rowsToAttributes', () => {
		const original = {
			name: 'Recipe',
			ingredients: [
				{ name: 'Flour', quantity: '200', unit: 'g' },
				{ name: 'Sugar', quantity: '50', unit: 'g' }
			]
		};

		expect(rowsToAttributes(attributesToRows(original))).toEqual(original);
	});
});

describe('rowsToAttributes with schema', () => {
	it('coerces number fields to JS numbers', () => {
		const rows: AttributeRow[] = [{ key: 'year', value: '1979' }];
		const result = rowsToAttributes(rows, schema({ year: { title: 'Year', type: 'number' } }));
		expect(result).toEqual({ year: 1979 });
		expect(typeof result.year).toBe('number');
	});

	it('omits empty number fields rather than sending an empty string', () => {
		const rows: AttributeRow[] = [{ key: 'year', value: '' }];
		expect(rowsToAttributes(rows, schema({ year: { title: 'Year', type: 'number' } }))).toEqual({});
	});

	it('passes non-numeric strings through for number fields (backend validates)', () => {
		const rows: AttributeRow[] = [{ key: 'year', value: 'abc' }];
		expect(rowsToAttributes(rows, schema({ year: { title: 'Year', type: 'number' } }))).toEqual({
			year: 'abc'
		});
	});

	it('omits a top-level boolean that was cleared to "not recorded"', () => {
		const rows: AttributeRow[] = [
			{ key: 'signed', value: '' },
			{ key: 'owned', value: 'false' }
		];
		expect(
			rowsToAttributes(
				rows,
				schema({
					signed: { title: 'Signed?', type: 'boolean' },
					owned: { title: 'Owned', type: 'boolean' }
				})
			)
		).toEqual({ owned: false });
	});

	it('coerces boolean fields: "true" → true, "false" → false', () => {
		const rows: AttributeRow[] = [
			{ key: 'owned', value: 'true' },
			{ key: 'sold', value: 'false' }
		];
		expect(
			rowsToAttributes(
				rows,
				schema({
					owned: { title: 'Owned', type: 'boolean' },
					sold: { title: 'Sold', type: 'boolean' }
				})
			)
		).toEqual({ owned: true, sold: false });
	});

	it('coerces numeric sub-fields inside group rows', () => {
		const rows: AttributeRow[] = [{ key: 'prices', value: [{ currency: 'GBP', amount: '12.50' }] }];
		expect(
			rowsToAttributes(
				rows,
				schema({
					prices: {
						title: 'Prices',
						type: 'array',
						items: {
							type: 'object',
							properties: {
								currency: { title: 'Currency', type: 'string' },
								amount: { title: 'Amount', type: 'number' }
							}
						}
					}
				})
			)
		).toEqual({ prices: [{ currency: 'GBP', amount: 12.5 }] });
	});

	it('omits an empty choice and an empty date, keeps empty text', () => {
		const rows: AttributeRow[] = [
			{ key: 'status', value: '' },
			{ key: 'released', value: '' },
			{ key: 'name', value: '' }
		];
		expect(
			rowsToAttributes(
				rows,
				schema({
					status: { title: 'Status', type: 'string', enum: ['A', 'B'] },
					released: { title: 'Released', type: 'string', format: 'date' },
					name: { title: 'Name', type: 'string' }
				})
			)
		).toEqual({ name: '' });
	});

	describe('group rows with blank cells', () => {
		const groupSchema = schema({
			recipe: {
				title: 'Recipe',
				type: 'array',
				items: {
					type: 'object',
					properties: {
						name: { title: 'Name', type: 'string' },
						qty: { title: 'Qty', type: 'number' },
						added: { title: 'Added', type: 'string', format: 'date' }
					}
				}
			}
		});

		it('omits blank number and date cells but keeps blank text', () => {
			const rows: AttributeRow[] = [
				{
					key: 'recipe',
					value: [
						{ name: 'Flour', qty: '', added: '' },
						{ name: '', qty: '', added: '' }
					]
				}
			];
			expect(rowsToAttributes(rows, groupSchema)).toEqual({
				recipe: [{ name: 'Flour' }, { name: '' }]
			});
		});

		it('keeps a row with no keys as an empty object', () => {
			const schemaNoText = schema({
				recipe: {
					title: 'Recipe',
					type: 'array',
					items: { type: 'object', properties: { qty: { title: 'Qty', type: 'number' } } }
				}
			});
			const rows: AttributeRow[] = [{ key: 'recipe', value: [{ qty: '' }] }];
			expect(rowsToAttributes(rows, schemaNoText)).toEqual({ recipe: [{}] });
		});

		it('omits a blank rating cell and keeps a chosen one', () => {
			const ratingSchema = schema({
				reviews: {
					title: 'Reviews',
					type: 'array',
					items: {
						type: 'object',
						properties: {
							score: {
								title: 'Score',
								type: 'number',
								minimum: 1,
								maximum: 5,
								multipleOf: 1,
								'x-menagerist': { kind: 'rating' }
							}
						}
					}
				}
			});
			const rows: AttributeRow[] = [{ key: 'reviews', value: [{ score: '' }, { score: '4' }] }];
			expect(rowsToAttributes(rows, ratingSchema)).toEqual({ reviews: [{}, { score: 4 }] });
		});

		it('does not throw for an array of non-object items', () => {
			const rows: AttributeRow[] = [{ key: 'tags', value: [] }];
			const s = schema({
				tags: { title: 'Tags', type: 'array', items: { type: 'string' } }
			} as unknown as AttributesSchema['properties']);
			expect(() => rowsToAttributes(rows, s)).not.toThrow();
		});

		it('omits a blank choice cell and keeps a chosen one', () => {
			const choiceSchema = schema({
				cast: {
					title: 'Cast',
					type: 'array',
					items: {
						type: 'object',
						properties: {
							role: {
								title: 'Role',
								type: 'string',
								enum: ['Lead', 'Support'],
								'x-menagerist': { kind: 'choice' }
							}
						}
					}
				}
			});
			const rows: AttributeRow[] = [{ key: 'cast', value: [{ role: '' }, { role: 'Lead' }] }];
			expect(rowsToAttributes(rows, choiceSchema)).toEqual({ cast: [{}, { role: 'Lead' }] });
		});

		it('coerces a quantity cell and omits it only when both sub-values are blank', () => {
			const quantitySchema = schema({
				ingredients: {
					title: 'Ingredients',
					type: 'array',
					items: {
						type: 'object',
						properties: {
							name: { title: 'Name', type: 'string' },
							amount: {
								title: 'Amount',
								type: 'object',
								properties: {
									value: { title: 'Value', type: 'number' },
									unit: { title: 'Unit', type: 'string' }
								},
								'x-menagerist': { kind: 'quantity' }
							}
						}
					}
				}
			});
			const rows: AttributeRow[] = [
				{ key: 'ingredients', value: [{ name: 'Flour', amount: { value: '180', unit: 'g' } }] }
			];
			expect(rowsToAttributes(rows, quantitySchema)).toEqual({
				ingredients: [{ name: 'Flour', amount: { value: 180, unit: 'g' } }]
			});

			const blankAmount: AttributeRow[] = [
				{ key: 'ingredients', value: [{ name: 'Salt', amount: { value: '', unit: '' } }] }
			];
			expect(rowsToAttributes(blankAmount, quantitySchema)).toEqual({
				ingredients: [{ name: 'Salt' }]
			});

			const unitOnly: AttributeRow[] = [
				{ key: 'ingredients', value: [{ name: 'Pinch', amount: { value: '', unit: 'g' } }] }
			];
			expect(rowsToAttributes(unitOnly, quantitySchema)).toEqual({
				ingredients: [{ name: 'Pinch', amount: { unit: 'g' } }]
			});
		});

		it('round-trips a quantity column through attributesToRows then rowsToAttributes', () => {
			const quantitySchema = schema({
				ingredients: {
					title: 'Ingredients',
					type: 'array',
					items: {
						type: 'object',
						properties: {
							name: { title: 'Name', type: 'string' },
							amount: {
								title: 'Amount',
								type: 'object',
								properties: {
									value: { title: 'Value', type: 'number' },
									unit: { title: 'Unit', type: 'string' }
								},
								'x-menagerist': { kind: 'quantity' }
							}
						}
					}
				}
			});
			const original = { ingredients: [{ name: 'Flour', amount: { value: 180, unit: 'g' } }] };
			expect(rowsToAttributes(attributesToRows(original, quantitySchema), quantitySchema)).toEqual(
				original
			);
		});
	});

	it('passes unknown keys through as strings regardless of schema', () => {
		const rows: AttributeRow[] = [{ key: 'notes', value: 'free text' }];
		expect(rowsToAttributes(rows, schema({ year: { title: 'Year', type: 'number' } }))).toEqual({
			notes: 'free text'
		});
	});

	it('round-trips typed values: attributesToRows → rowsToAttributes restores original types', () => {
		const original = { year: 1979, owned: true, title: 'Alien' };
		const s = schema({
			year: { title: 'Year', type: 'number' },
			owned: { title: 'Owned', type: 'boolean' },
			title: { title: 'Title', type: 'string' }
		});
		expect(rowsToAttributes(attributesToRows(original), s)).toEqual(original);
	});

	describe('composite (type: object) fields', () => {
		const quantitySchema = schema({
			weight: {
				title: 'Weight',
				type: 'object',
				properties: {
					value: { title: 'Value', type: 'number' },
					unit: { title: 'Unit', type: 'string' }
				}
			}
		});

		it('attributesToRows hydrates a schema-defined object as an editable flat row', () => {
			expect(attributesToRows({ weight: { value: 180, unit: 'g' } }, quantitySchema)).toEqual([
				{ key: 'weight', value: { value: '180', unit: 'g' } }
			]);
		});

		it('attributesToRows keeps an object under an unknown key as read-only json', () => {
			expect(attributesToRows({ weight: { value: 180, unit: 'g' } })).toEqual([
				{
					key: 'weight',
					value: '{"value":180,"unit":"g"}',
					kind: 'json',
					raw: { value: 180, unit: 'g' }
				}
			]);
		});

		it('rowsToAttributes coerces and round-trips a composite value', () => {
			const rows: AttributeRow[] = [{ key: 'weight', value: { value: '180', unit: 'g' } }];
			expect(rowsToAttributes(rows, quantitySchema)).toEqual({ weight: { value: 180, unit: 'g' } });
		});

		it('rowsToAttributes omits a composite field whose sub-values are all blank', () => {
			const rows: AttributeRow[] = [{ key: 'weight', value: { value: '', unit: '' } }];
			expect(rowsToAttributes(rows, quantitySchema)).toEqual({});
		});

		it('rowsToAttributes keeps a partially filled composite value, blank text sub-value and all', () => {
			const rows: AttributeRow[] = [{ key: 'weight', value: { value: '180', unit: '' } }];
			// unit is a plain text sub-value, so a blank one is kept, same as a group's text cells.
			expect(rowsToAttributes(rows, quantitySchema)).toEqual({ weight: { value: 180, unit: '' } });
		});

		it('round-trips a composite value end to end', () => {
			const original = { weight: { value: 180, unit: 'g' } };
			expect(rowsToAttributes(attributesToRows(original, quantitySchema), quantitySchema)).toEqual(
				original
			);
		});
	});

	describe('ordered list (type: array, items: type string) fields', () => {
		const listSchema = schema({
			instructions: { title: 'Instructions', type: 'array', items: { type: 'string' } }
		});

		it('attributesToRows hydrates a schema-defined string array as an editable list', () => {
			expect(attributesToRows({ instructions: ['Preheat', 'Mix'] }, listSchema)).toEqual([
				{ key: 'instructions', value: ['Preheat', 'Mix'] }
			]);
		});

		it('attributesToRows keeps a string array under an unknown key as read-only json', () => {
			expect(attributesToRows({ instructions: ['Preheat', 'Mix'] })).toEqual([
				{
					key: 'instructions',
					value: '["Preheat","Mix"]',
					kind: 'json',
					raw: ['Preheat', 'Mix']
				}
			]);
		});

		it('rowsToAttributes drops a blank item and keeps the rest, in order', () => {
			const rows: AttributeRow[] = [{ key: 'instructions', value: ['Preheat', '', 'Mix', '  '] }];
			expect(rowsToAttributes(rows, listSchema)).toEqual({ instructions: ['Preheat', 'Mix'] });
		});

		it('rowsToAttributes omits the key when every item is blank', () => {
			const rows: AttributeRow[] = [{ key: 'instructions', value: ['', '  '] }];
			expect(rowsToAttributes(rows, listSchema)).toEqual({});
		});

		it('round-trips a list value end to end', () => {
			const original = { instructions: ['Preheat', 'Mix', 'Bake'] };
			expect(rowsToAttributes(attributesToRows(original, listSchema), listSchema)).toEqual(
				original
			);
		});
	});

	describe('checklist (array of {text, done}) fields', () => {
		const checklistSchema = schema({
			packing_list: {
				title: 'Packing list',
				type: 'array',
				items: {
					type: 'object',
					properties: {
						text: { title: 'Text', type: 'string' },
						done: { title: 'Done', type: 'boolean' }
					}
				},
				'x-menagerist': { kind: 'checklist' }
			}
		});

		it('attributesToRows hydrates a schema-defined checklist as {text, done} rows', () => {
			expect(
				attributesToRows(
					{ packing_list: [{ text: 'Passport', done: true }, { text: 'Charger' }] },
					checklistSchema
				)
			).toEqual([
				{
					key: 'packing_list',
					value: [
						{ text: 'Passport', done: true },
						{ text: 'Charger', done: false }
					]
				}
			]);
		});

		it('does not confuse a checklist with a plain group (array of objects)', () => {
			// Same raw shape (array of plain objects) as a `group` field's rows; only the
			// schema's explicit checklist kind should route it to {text, done} rows, not
			// the generic group stringify/json path.
			const rows = attributesToRows(
				{ packing_list: [{ text: 'Passport', done: true }] },
				checklistSchema
			);
			expect(rows[0].kind).toBeUndefined();
			expect(rows[0].raw).toBeUndefined();
		});

		it('attributesToRows keeps a checklist-shaped array under an unknown key as generic group rows', () => {
			// With no schema to say "checklist", this array-of-objects value falls back to the
			// same generic stringified-cell treatment any group/table value gets.
			const value = [{ text: 'Passport', done: true }];
			expect(attributesToRows({ packing_list: value })).toEqual([
				{
					key: 'packing_list',
					value: [{ text: 'Passport', done: 'true' }],
					kind: 'json',
					raw: value
				}
			]);
		});

		it('rowsToAttributes drops a blank-text item, tick and all, and keeps the rest', () => {
			const rows: AttributeRow[] = [
				{
					key: 'packing_list',
					value: [
						{ text: 'Passport', done: true },
						{ text: '', done: true },
						{ text: 'Charger', done: false }
					]
				}
			];
			expect(rowsToAttributes(rows, checklistSchema)).toEqual({
				packing_list: [
					{ text: 'Passport', done: true },
					{ text: 'Charger', done: false }
				]
			});
		});

		it('rowsToAttributes omits the key when every item is blank', () => {
			const rows: AttributeRow[] = [{ key: 'packing_list', value: [{ text: '  ', done: false }] }];
			expect(rowsToAttributes(rows, checklistSchema)).toEqual({});
		});

		it('round-trips a checklist value end to end', () => {
			const original = {
				packing_list: [
					{ text: 'Passport', done: true },
					{ text: 'Charger', done: false }
				]
			};
			expect(
				rowsToAttributes(attributesToRows(original, checklistSchema), checklistSchema)
			).toEqual(original);
		});
	});
});

describe('@cfworker/json-schema validation', () => {
	const mkSchema = (properties: AttributesSchema['properties'], required?: string[]): object => ({
		$schema: 'https://json-schema.org/draft/2020-12/schema',
		type: 'object',
		properties,
		...(required ? { required } : {})
	});

	it('passes valid data', () => {
		const v = new Validator(
			mkSchema({ year: { title: 'Year', type: 'number' } }),
			'2020-12',
			false
		);
		expect(v.validate({ year: 2020 }).valid).toBe(true);
	});

	it('fails on type mismatch and reports instanceLocation as #/field', () => {
		const v = new Validator(
			mkSchema({ year: { title: 'Year', type: 'number' } }),
			'2020-12',
			false
		);
		const result = v.validate({ year: 'bad' });
		expect(result.valid).toBe(false);
		const keys = result.errors.map((e) => e.instanceLocation.replace(/^#\/?/, '')).filter(Boolean);
		expect(keys).toContain('year');
	});

	it('collects multiple errors when shortCircuit is false', () => {
		const v = new Validator(
			mkSchema(
				{ year: { title: 'Year', type: 'number' }, title: { title: 'Title', type: 'string' } },
				['year', 'title']
			),
			'2020-12',
			false
		);
		expect(v.validate({}).valid).toBe(false);
		expect(v.validate({}).errors.length).toBeGreaterThan(1);
	});

	it('ignores the x-menagerist namespace without throwing or enforcing required', () => {
		const s: object = {
			$schema: 'https://json-schema.org/draft/2020-12/schema',
			type: 'object',
			properties: {
				bio: { title: 'Bio', type: 'string', 'x-menagerist': { kind: 'longtext' } }
			},
			'x-menagerist': { version: 1, layout: [{ key: 'bio' }], required: ['bio'] }
		};
		const v = new Validator(s, '2020-12', false);
		expect(() => v.validate({ bio: 'text' })).not.toThrow();
		expect(v.validate({ bio: 'text' }).valid).toBe(true);
	});

	it('validates date format', () => {
		const v = new Validator(
			mkSchema({ dob: { title: 'DoB', type: 'string', format: 'date' } }),
			'2020-12',
			false
		);
		expect(v.validate({ dob: '2024-01-15' }).valid).toBe(true);
		expect(v.validate({ dob: 'not-a-date' }).valid).toBe(false);
	});
});
