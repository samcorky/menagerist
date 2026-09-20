import { register, descriptorForProp, getDescriptor } from '../registry';
import GroupInput from './GroupInput.svelte';
import GroupExtras from './GroupExtras.svelte';
import GroupView from './GroupView.svelte';
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
				f.subFields.map((sf) => {
					const d = getDescriptor(sf.kind);
					const prop: JsonSchemaProperty = d
						? d.toSchema({
								key: sf.key,
								label: sf.label,
								kind: sf.kind,
								required: false,
								options: [],
								subFields: []
							})
						: { title: sf.label, type: 'string' };
					return [sf.key, prop];
				})
			)
		}
	}),
	fromSchema: (key, prop, required) => {
		if (prop.type !== 'array') return null;
		return {
			key,
			label: prop.title,
			kind: 'group',
			required,
			options: [],
			subFields: Object.entries(prop.items.properties).map(([sk, sp]) => ({
				key: sk,
				label: sp.title,
				kind: descriptorForProp(sp)?.kind ?? 'text'
			}))
		};
	},
	InputWidget: GroupInput,
	EditorExtras: GroupExtras,
	ViewWidget: GroupView
});
