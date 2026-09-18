<script lang="ts" module>
	export type JsonSchemaProperty =
		| { title: string; type: 'string'; 'x-multiline'?: true }
		| { title: string; type: 'string'; format: 'date' }
		| { title: string; type: 'string'; enum: string[] }
		| { title: string; type: 'number' }
		| { title: string; type: 'boolean' }
		| {
				title: string;
				type: 'array';
				items: { type: 'object'; properties: Record<string, JsonSchemaProperty> };
		  };

	export type AttributesSchema = {
		$schema: 'https://json-schema.org/draft/2020-12/schema';
		type: 'object';
		properties: Record<string, JsonSchemaProperty>;
		required?: string[];
	};

	type FieldKind = 'text' | 'longtext' | 'number' | 'boolean' | 'date' | 'choice' | 'group';

	type EditorSubField = { key: string; label: string; kind: Exclude<FieldKind, 'group'> };

	type EditorField = {
		key: string;
		label: string;
		kind: FieldKind;
		required: boolean;
		options: string[];
		subFields: EditorSubField[];
	};

	function propertyToField(key: string, prop: JsonSchemaProperty, required: boolean): EditorField {
		const base = { key, label: prop.title, required, options: [], subFields: [] };
		if (prop.type === 'array') {
			return {
				...base,
				kind: 'group',
				subFields: Object.entries(prop.items.properties).map(([sk, sp]) => ({
					key: sk,
					label: sp.title,
					kind: subPropertyKind(sp)
				}))
			};
		}
		return { ...base, kind: scalarKind(prop) };
	}

	function scalarKind(prop: JsonSchemaProperty): Exclude<FieldKind, 'group'> {
		if (prop.type === 'array') return 'text';
		if (prop.type === 'number') return 'number';
		if (prop.type === 'boolean') return 'boolean';
		if ('format' in prop && prop.format === 'date') return 'date';
		if ('enum' in prop) return 'choice';
		if ('x-multiline' in prop && prop['x-multiline']) return 'longtext';
		return 'text';
	}

	function subPropertyKind(prop: JsonSchemaProperty): Exclude<FieldKind, 'group'> {
		return scalarKind(prop);
	}

	function fieldToProperty(f: EditorField): JsonSchemaProperty {
		switch (f.kind) {
			case 'number':
				return { title: f.label, type: 'number' };
			case 'boolean':
				return { title: f.label, type: 'boolean' };
			case 'date':
				return { title: f.label, type: 'string', format: 'date' };
			case 'choice':
				return { title: f.label, type: 'string', enum: f.options };
			case 'longtext':
				return { title: f.label, type: 'string', 'x-multiline': true };
			case 'group':
				return {
					title: f.label,
					type: 'array',
					items: {
						type: 'object',
						properties: Object.fromEntries(
							f.subFields.map((sf) => [sf.key, subFieldToProperty(sf)])
						)
					}
				};
			default:
				return { title: f.label, type: 'string' };
		}
	}

	function subFieldToProperty(sf: EditorSubField): JsonSchemaProperty {
		switch (sf.kind) {
			case 'number':
				return { title: sf.label, type: 'number' };
			case 'boolean':
				return { title: sf.label, type: 'boolean' };
			case 'date':
				return { title: sf.label, type: 'string', format: 'date' };
			case 'choice':
				return { title: sf.label, type: 'string', enum: [] };
			case 'longtext':
				return { title: sf.label, type: 'string', 'x-multiline': true };
			default:
				return { title: sf.label, type: 'string' };
		}
	}

	function schemaToFields(schema: AttributesSchema | null): EditorField[] {
		if (!schema) return [];
		const required = new Set(schema.required ?? []);
		return Object.entries(schema.properties).map(([key, prop]) =>
			propertyToField(key, prop, required.has(key))
		);
	}

	function fieldsToSchema(fields: EditorField[]): AttributesSchema | null {
		if (fields.length === 0) return null;
		const properties: Record<string, JsonSchemaProperty> = {};
		const required: string[] = [];
		for (const f of fields) {
			if (!f.key) continue;
			properties[f.key] = fieldToProperty(f);
			if (f.required) required.push(f.key);
		}
		return {
			$schema: 'https://json-schema.org/draft/2020-12/schema',
			type: 'object',
			properties,
			...(required.length > 0 ? { required } : {})
		};
	}
</script>

<script lang="ts">
	import { Plus, X } from '@lucide/svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import { slugify } from '$lib/utils.js';

	let { schema = $bindable<AttributesSchema | null>(null) }: { schema?: AttributesSchema | null } =
		$props();

	let fields = $state<EditorField[]>(schemaToFields(schema));

	$effect(() => {
		schema = fieldsToSchema(fields);
	});

	function addField() {
		fields = [
			...fields,
			{ key: '', label: '', kind: 'text', required: false, options: [], subFields: [] }
		];
	}

	function removeField(index: number) {
		fields = fields.filter((_, i) => i !== index);
	}

	function handleLabelChange(index: number, value: string) {
		fields = fields.map((f, i) => {
			if (i !== index) return f;
			return { ...f, label: value, key: f.key || slugify(value) };
		});
	}

	function addSubField(field: EditorField) {
		field.subFields = [
			...field.subFields,
			{ key: '', label: '', kind: 'text' as Exclude<FieldKind, 'group'> }
		];
	}

	function removeSubField(field: EditorField, index: number) {
		field.subFields = field.subFields.filter((_, i) => i !== index);
	}

	function handleSubFieldLabelChange(field: EditorField, index: number, value: string) {
		field.subFields = field.subFields.map((sf, i) => {
			if (i !== index) return sf;
			return { ...sf, label: value, key: sf.key || slugify(value) };
		});
	}
</script>

{#snippet fieldRow(
	field: EditorField,
	allowGroup: boolean,
	onLabelChange: (value: string) => void,
	onRemove: () => void
)}
	<div class="flex flex-wrap items-center gap-2">
		<Input
			value={field.label}
			placeholder="Label"
			class="w-40"
			aria-label="Field label"
			oninput={(e) => onLabelChange((e.target as HTMLInputElement).value)}
		/>
		<select
			bind:value={field.kind}
			class="h-9 rounded-md border border-input bg-background px-2 py-1 text-sm shadow-sm focus:ring-1 focus:ring-ring focus:outline-none"
			aria-label="Field kind"
		>
			<option value="text">Text</option>
			<option value="number">Number</option>
			<option value="boolean">Yes/No</option>
			<option value="date">Date</option>
			<option value="choice">Choice</option>
			<option value="longtext">Long text</option>
			{#if allowGroup}
				<option value="group">Group</option>
			{/if}
		</select>
		<label class="flex items-center gap-1.5 text-sm">
			<input
				type="checkbox"
				bind:checked={field.required}
				class="h-4 w-4 rounded border-input accent-primary"
			/>
			Required
		</label>
		<Button type="button" variant="ghost" size="icon" onclick={onRemove} aria-label="Remove field">
			<X class="size-4" />
		</Button>
	</div>

	{#if allowGroup && field.kind === 'group'}
		<div class="ml-6 space-y-2 border-l border-input pl-4">
			{#each field.subFields as subField, si (si)}
				{@render subFieldRow(
					subField,
					() => handleSubFieldLabelChange(field, si, subField.label),
					() => removeSubField(field, si)
				)}
			{/each}
			<Button type="button" variant="outline" size="sm" onclick={() => addSubField(field)}>
				<Plus class="size-4" />
				Add sub-field
			</Button>
		</div>
	{/if}
{/snippet}

{#snippet subFieldRow(subField: EditorSubField, onLabelChange: () => void, onRemove: () => void)}
	<div class="flex flex-wrap items-center gap-2">
		<Input
			value={subField.label}
			placeholder="Label"
			class="w-40"
			aria-label="Sub-field label"
			oninput={(e) => {
				subField.label = (e.target as HTMLInputElement).value;
				if (!subField.key) subField.key = slugify(subField.label);
				onLabelChange();
			}}
		/>
		<select
			bind:value={subField.kind}
			class="h-9 rounded-md border border-input bg-background px-2 py-1 text-sm shadow-sm focus:ring-1 focus:ring-ring focus:outline-none"
			aria-label="Sub-field kind"
		>
			<option value="text">Text</option>
			<option value="number">Number</option>
			<option value="boolean">Yes/No</option>
			<option value="date">Date</option>
			<option value="longtext">Long text</option>
		</select>
		<Button
			type="button"
			variant="ghost"
			size="icon"
			onclick={onRemove}
			aria-label="Remove sub-field"
		>
			<X class="size-4" />
		</Button>
	</div>
{/snippet}

<div class="space-y-3">
	<Label>Fields</Label>

	{#each fields as field, i (i)}
		{@render fieldRow(
			field,
			true,
			(value) => handleLabelChange(i, value),
			() => removeField(i)
		)}
	{/each}

	<Button type="button" variant="outline" size="sm" onclick={addField}>
		<Plus class="size-4" />
		Add field
	</Button>
</div>
