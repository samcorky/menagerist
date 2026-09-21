import { register, fieldFromProperty, getDescriptor, propertyFromField } from '../registry';
import GroupInput from './GroupInput.svelte';
import GroupExtras from './GroupExtras.svelte';
import GroupView from './GroupView.svelte';
import { resolvePendingKeys } from '$lib/field-key';
import type { EditorField, JsonSchemaProperty } from '$lib/schema-types';

register({
	kind: 'group',
	label: 'Group',
	canBeSubField: false,
	toSchema: (f: EditorField): JsonSchemaProperty => ({
		title: f.label,
		type: 'array',
		items: {
			type: 'object',
			properties: Object.fromEntries(
				resolvePendingKeys(f.subFields).map((sf) => [
					sf.key,
					propertyFromField({
						key: sf.key,
						label: sf.label,
						kind: sf.kind,
						required: false,
						options: [],
						subFields: [],
						meta: sf.meta,
						raw: sf.raw
					})
				])
			)
		}
	}),
	fromSchema: (key, prop, required) => {
		if (prop.type !== 'array') return null;
		if ((prop.items as { type?: string } | undefined)?.type !== 'object') return null;
		return {
			key,
			label: prop.title,
			kind: 'group',
			required,
			options: [],
			subFields: Object.entries(prop.items.properties ?? {}).map(([sk, sp]) => {
				const sub = fieldFromProperty(sk, sp, false);
				const canNest = getDescriptor(sub.kind)?.canBeSubField !== false;
				if (sub.kind !== 'opaque' && canNest) {
					return { key: sk, label: sp.title, kind: sub.kind, meta: sub.meta };
				}
				return { key: sk, label: sp.title, kind: 'opaque', raw: sp as Record<string, unknown> };
			})
		};
	},
	InputWidget: GroupInput,
	EditorExtras: GroupExtras,
	ViewWidget: GroupView
});
