<script lang="ts" module>
	import { normalise, isSectionItem, type XLayout } from '$lib/layout';

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
		'x-layout'?: XLayout;
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

	type EditorSection = {
		_section: true;
		id: string;
		sectionLabel: string;
		fields: EditorField[];
	};

	type EditorItem = EditorField | EditorSection;

	function isSection(item: EditorItem): item is EditorSection {
		return '_section' in item;
	}

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

	function schemaToItems(schema: AttributesSchema | null): EditorItem[] {
		if (!schema) return [];
		const required = new Set(schema.required ?? []);
		const layout = normalise(schema['x-layout'], schema.properties);
		return layout.flatMap((layoutItem): EditorItem[] => {
			if (isSectionItem(layoutItem)) {
				return [
					{
						_section: true,
						id: layoutItem.id,
						sectionLabel: layoutItem.section,
						fields: layoutItem.items
							.filter((i) => i.key in schema.properties)
							.map((i) => propertyToField(i.key, schema.properties[i.key], required.has(i.key)))
					}
				];
			} else {
				if (!(layoutItem.key in schema.properties)) return [];
				return [
					propertyToField(
						layoutItem.key,
						schema.properties[layoutItem.key],
						required.has(layoutItem.key)
					)
				];
			}
		});
	}

	function itemsToSchema(items: EditorItem[]): AttributesSchema | null {
		const properties: Record<string, JsonSchemaProperty> = {};
		const required: string[] = [];
		const layout: XLayout = [];

		for (const item of items) {
			if (isSection(item)) {
				const sectionLayout: { key: string }[] = [];
				for (const f of item.fields) {
					if (!f.key) continue;
					properties[f.key] = fieldToProperty(f);
					if (f.required) required.push(f.key);
					sectionLayout.push({ key: f.key });
				}
				if (sectionLayout.length > 0) {
					layout.push({
						id: item.id,
						section: item.sectionLabel || 'Section',
						items: sectionLayout
					});
				}
			} else {
				if (!item.key) continue;
				properties[item.key] = fieldToProperty(item);
				if (item.required) required.push(item.key);
				layout.push({ key: item.key });
			}
		}

		if (Object.keys(properties).length === 0) return null;
		return {
			$schema: 'https://json-schema.org/draft/2020-12/schema',
			type: 'object',
			properties,
			'x-layout': layout,
			...(required.length > 0 ? { required } : {})
		};
	}
</script>

<script lang="ts">
	import { FolderOpen, Plus, X } from '@lucide/svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import { slugify } from '$lib/utils.js';

	let { schema = $bindable<AttributesSchema | null>(null) }: { schema?: AttributesSchema | null } =
		$props();

	let items = $state<EditorItem[]>(schemaToItems(schema));

	$effect(() => {
		schema = itemsToSchema(items);
	});

	function addField() {
		items = [
			...items,
			{ key: '', label: '', kind: 'text', required: false, options: [], subFields: [] }
		];
	}

	function addSection() {
		items = [
			...items,
			{
				_section: true as const,
				id:
					typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
						? crypto.randomUUID()
						: `${Date.now()}-${Math.random().toString(16).slice(2)}-${Math.random().toString(16).slice(2)}`,
				sectionLabel: '',
				fields: []
			}
		];
	}

	function removeItem(index: number) {
		items = items.filter((_, i) => i !== index);
	}

	function handleFieldLabelChange(index: number, value: string) {
		items = items.map((item, i) => {
			if (i !== index || isSection(item)) return item;
			return { ...item, label: value, key: slugify(value) };
		});
	}

	function handleSectionLabelChange(index: number, value: string) {
		items = items.map((item, i) => {
			if (i !== index || !isSection(item)) return item;
			return { ...item, sectionLabel: value };
		});
	}

	function addFieldToSection(sectionIndex: number) {
		items = items.map((item, i) => {
			if (i !== sectionIndex || !isSection(item)) return item;
			return {
				...item,
				fields: [
					...item.fields,
					{ key: '', label: '', kind: 'text' as const, required: false, options: [], subFields: [] }
				]
			};
		});
	}

	function removeFieldFromSection(sectionIndex: number, fieldIndex: number) {
		items = items.map((item, i) => {
			if (i !== sectionIndex || !isSection(item)) return item;
			return { ...item, fields: item.fields.filter((_, fi) => fi !== fieldIndex) };
		});
	}

	function handleSectionFieldLabelChange(sectionIndex: number, fieldIndex: number, value: string) {
		items = items.map((item, i) => {
			if (i !== sectionIndex || !isSection(item)) return item;
			return {
				...item,
				fields: item.fields.map((f, fi) => {
					if (fi !== fieldIndex) return f;
					return { ...f, label: value, key: slugify(value) };
				})
			};
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
			return { ...sf, label: value, key: slugify(value) };
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

	{#each items as item, i (i)}
		{#if isSection(item)}
			<div class="space-y-2 rounded-md border border-input bg-muted/30 p-3">
				<div class="flex items-center gap-2">
					<FolderOpen class="size-4 shrink-0 text-muted-foreground" />
					<Input
						value={item.sectionLabel}
						placeholder="Section name"
						class="h-8 w-44 text-sm font-medium"
						aria-label="Section name"
						oninput={(e) => handleSectionLabelChange(i, (e.target as HTMLInputElement).value)}
					/>
					<span class="text-xs text-muted-foreground">Section</span>
					<Button
						type="button"
						variant="ghost"
						size="icon"
						class="ml-auto size-7"
						onclick={() => removeItem(i)}
						aria-label="Remove section"
					>
						<X class="size-3.5" />
					</Button>
				</div>
				<div class="ml-2 space-y-2 border-l border-input pl-3">
					{#each item.fields as field, fi (fi)}
						{@render fieldRow(
							field,
							false,
							(value) => handleSectionFieldLabelChange(i, fi, value),
							() => removeFieldFromSection(i, fi)
						)}
					{/each}
					<Button
						type="button"
						variant="ghost"
						size="sm"
						class="h-7 text-xs"
						onclick={() => addFieldToSection(i)}
					>
						<Plus class="size-3" />
						Add field
					</Button>
				</div>
			</div>
		{:else}
			{@render fieldRow(
				item,
				true,
				(value) => handleFieldLabelChange(i, value),
				() => removeItem(i)
			)}
		{/if}
	{/each}

	<div class="flex gap-2">
		<Button type="button" variant="outline" size="sm" onclick={addField}>
			<Plus class="size-4" />
			Add field
		</Button>
		<Button type="button" variant="outline" size="sm" onclick={addSection}>
			<FolderOpen class="size-4" />
			Add section
		</Button>
	</div>
</div>
