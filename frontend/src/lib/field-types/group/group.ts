import { register, fieldFromProperty, getDescriptor, propertyFromField } from '../registry';
import GroupInput from './GroupInput.svelte';
import GroupExtras from './GroupExtras.svelte';
import GroupView from './GroupView.svelte';
import { orderedColumns } from './columns';
import { resolvePendingKeys } from '$lib/field-key';
import { withPropMeta } from '$lib/schema-meta';
import type { EditorField, JsonSchemaProperty } from '$lib/schema-types';

register({
	kind: 'group',
	// UI label only (WI-19a); the code name stays 'group' so stored definitions don't change.
	label: 'Table',
	canBeSubField: false,
	toSchema: (f: EditorField): JsonSchemaProperty => {
		const subFields = resolvePendingKeys(f.subFields);
		// JSONB does not preserve nested object key order, so the column order is
		// recorded explicitly (see field-types/group/columns.ts).
		return withPropMeta(
			{
				title: f.label,
				type: 'array',
				items: {
					type: 'object',
					properties: Object.fromEntries(
						subFields.map((sf) => [
							sf.key,
							propertyFromField({
								key: sf.key,
								label: sf.label,
								kind: sf.kind,
								required: false,
								options: [],
								subFields: [],
								config: sf.config,
								meta: sf.meta,
								raw: sf.raw
							})
						])
					)
				}
			},
			{ columns: subFields.map((sf) => sf.key) }
		);
	},
	fromSchema: (key, prop, required) => {
		if (prop.type !== 'array') return null;
		if ((prop.items as { type?: string } | undefined)?.type !== 'object') return null;
		return {
			key,
			label: prop.title,
			kind: 'group',
			required,
			options: [],
			subFields: orderedColumns(prop).map(([sk, sp]) => {
				const sub = fieldFromProperty(sk, sp, false);
				const canNest = getDescriptor(sub.kind)?.canBeSubField !== false;
				if (sub.kind !== 'opaque' && canNest) {
					return {
						key: sk,
						label: sp.title,
						kind: sub.kind,
						meta: sub.meta,
						originalKind: sub.kind,
						...(sub.config ? { config: sub.config } : {})
					};
				}
				return { key: sk, label: sp.title, kind: 'opaque', raw: sp as Record<string, unknown> };
			})
		};
	},
	InputWidget: GroupInput,
	EditorExtras: GroupExtras,
	ViewWidget: GroupView
});
