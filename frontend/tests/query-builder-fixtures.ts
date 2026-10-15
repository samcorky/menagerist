import { buildCatalogue, type ItemTypeLike } from '$lib/query/fields';
import type { BuilderView } from '$lib/query/builder';

const meta = (kind: string, extra: Record<string, unknown> = {}) => ({
	'x-menagerist': { kind, ...extra }
});

export const itemTypes: ItemTypeLike[] = [
	{
		slug: 'film',
		label: 'Film',
		attributes_schema: {
			type: 'object',
			properties: {
				rating: { title: 'Rating', type: 'number', minimum: 1, maximum: 5, ...meta('rating') },
				runtime: {
					title: 'Runtime',
					type: 'number',
					minimum: 0,
					multipleOf: 1,
					...meta('duration')
				},
				price: {
					title: 'Price',
					type: 'object',
					properties: { value: { type: 'number' }, currency: { type: 'string' } },
					...meta('money')
				},
				released: { title: 'Released', type: 'string', format: 'date' },
				year: {
					title: 'Year',
					type: 'string',
					pattern: '^[0-9]{4}(-(0[1-9]|1[0-2])(-(0[1-9]|[12][0-9]|3[01]))?)?$'
				},
				format: { title: 'Format', type: 'string', enum: ['DVD', 'Blu-ray'] },
				note: { title: 'Note', type: 'string' },
				seen: { title: 'Seen', type: 'boolean' },
				stock: { title: 'Stock', type: 'number' },
				reorder_at: { title: 'Reorder at', type: 'number' },
				old: { title: 'Old', type: 'number', 'x-menagerist': { archived: true } },
				cast: {
					title: 'Cast',
					type: 'array',
					items: { type: 'object', properties: { role: { title: 'Role', type: 'string' } } }
				}
			}
		}
	},
	{ slug: 'book', label: 'Book', attributes_schema: null }
];

export const catalogue = buildCatalogue(itemTypes);

export function stubView(overrides: Partial<BuilderView> = {}): BuilderView {
	return {
		catalogue,
		numbers: new Map(),
		warned: new Set(),
		error: null,
		canAddCondition: true,
		canAddGroup: () => true,
		update() {},
		remove() {},
		addCondition() {},
		addGroup() {},
		setGroupOp() {},
		...overrides
	};
}
