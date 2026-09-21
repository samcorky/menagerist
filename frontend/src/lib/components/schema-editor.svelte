<script lang="ts" module>
	import { normalise, isSectionItem, type XLayout } from '$lib/layout';
	import type { JsonSchemaProperty, AttributesSchema, EditorField } from '$lib/schema-types';
	import {
		allDescriptors,
		getDescriptor,
		fieldFromProperty,
		propertyFromField
	} from '$lib/field-types';
	import { resolvePendingKeys } from '$lib/field-key';
	import { META_VERSION, readSchemaMeta, withSchemaMeta, type SchemaMeta } from '$lib/schema-meta';

	export type EditorSection = {
		_section: true;
		id: string;
		sectionLabel: string;
		fields: EditorField[];
	};

	export type EditorItem = EditorField | EditorSection;

	function isSection(item: EditorItem): item is EditorSection {
		return '_section' in item;
	}

	export function schemaToItems(schema: AttributesSchema | null): EditorItem[] {
		if (!schema) return [];
		const required = new Set(readSchemaMeta(schema).required ?? []);
		const layout = normalise(readSchemaMeta(schema).layout, schema.properties);
		return layout.flatMap((layoutItem): EditorItem[] => {
			if (isSectionItem(layoutItem)) {
				return [
					{
						_section: true,
						id: layoutItem.id,
						sectionLabel: layoutItem.section,
						fields: layoutItem.items
							.filter((i) => i.key in schema.properties)
							.map((i) => fieldFromProperty(i.key, schema.properties[i.key], required.has(i.key)))
					}
				];
			}
			if (!(layoutItem.key in schema.properties)) return [];
			return [
				fieldFromProperty(
					layoutItem.key,
					schema.properties[layoutItem.key],
					required.has(layoutItem.key)
				)
			];
		});
	}

	export function itemsToSchema(
		items: EditorItem[],
		baseMeta: SchemaMeta
	): AttributesSchema | null {
		// Resolve pending keys across the whole schema so they are unique globally.
		const all = items.flatMap((item) => (isSection(item) ? item.fields : [item]));
		const resolvedList = resolvePendingKeys(all);
		const resolved = new Map(all.map((f, i) => [f, resolvedList[i]]));

		const entries: [string, JsonSchemaProperty][] = [];
		const required: string[] = [];
		const layout: XLayout = [];

		for (const item of items) {
			if (isSection(item)) {
				const sectionLayout: { key: string }[] = [];
				for (const original of item.fields) {
					const f = resolved.get(original)!;
					if (!f.key) continue;
					entries.push([f.key, propertyFromField(f)]);
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
				const f = resolved.get(item)!;
				if (!f.key) continue;
				entries.push([f.key, propertyFromField(f)]);
				if (f.required) required.push(f.key);
				layout.push({ key: f.key });
			}
		}

		if (entries.length === 0) return null;
		const base = {
			$schema: 'https://json-schema.org/draft/2020-12/schema' as const,
			type: 'object' as const,
			properties: Object.fromEntries(entries) as Record<string, JsonSchemaProperty>
		};
		return withSchemaMeta(base, { ...baseMeta, version: META_VERSION, layout, required });
	}
</script>

<script lang="ts">
	import { untrack } from 'svelte';
	import { FolderOpen, Plus, X } from '@lucide/svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Label } from '$lib/components/ui/label/index.js';

	let { schema = $bindable<AttributesSchema | null>(null) }: { schema?: AttributesSchema | null } =
		$props();

	// Captured once so unknown root members survive round-trips.
	const baseMeta = untrack(() => readSchemaMeta(schema));
	let items = $state<EditorItem[]>(schemaToItems(schema));

	$effect(() => {
		schema = itemsToSchema(items, baseMeta);
	});

	function generateKey(): string {
		return typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
			? crypto.randomUUID()
			: `${Date.now()}-${Math.random().toString(16).slice(2)}-${Math.random().toString(16).slice(2)}`;
	}

	function addField() {
		items = [
			...items,
			{
				key: generateKey(),
				keyPending: true,
				label: '',
				kind: 'text',
				required: false,
				options: [],
				subFields: []
			}
		];
	}

	function addSection() {
		items = [
			...items,
			{ _section: true as const, id: generateKey(), sectionLabel: '', fields: [] }
		];
	}

	function removeItem(index: number) {
		items = items.filter((_, i) => i !== index);
	}

	function handleFieldLabelChange(index: number, value: string) {
		items = items.map((item, i) => {
			if (i !== index || isSection(item)) return item;
			return { ...item, label: value };
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
					{
						key: generateKey(),
						keyPending: true,
						label: '',
						kind: 'text',
						required: false,
						options: [],
						subFields: []
					}
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
				fields: item.fields.map((f, fi) => (fi !== fieldIndex ? f : { ...f, label: value }))
			};
		});
	}

	function handleFieldChange(index: number, field: EditorField) {
		items = items.map((item, i) => (i !== index || isSection(item) ? item : field));
	}

	function handleSectionFieldChange(sectionIndex: number, fieldIndex: number, field: EditorField) {
		items = items.map((item, i) => {
			if (i !== sectionIndex || !isSection(item)) return item;
			return { ...item, fields: item.fields.map((f, fi) => (fi !== fieldIndex ? f : field)) };
		});
	}
</script>

{#snippet fieldRow(
	field: EditorField,
	allowGroup: boolean,
	onLabelChange: (value: string) => void,
	onRemove: () => void,
	onFieldChange: (f: EditorField) => void
)}
	<div class="flex flex-wrap items-center gap-2">
		<Input
			value={field.label}
			placeholder="Label"
			class="w-40"
			aria-label="Field label"
			oninput={(e) => onLabelChange((e.target as HTMLInputElement).value)}
		/>
		{#if field.kind === 'opaque'}
			<span class="rounded border border-input px-1.5 text-xs text-muted-foreground">custom</span>
		{:else}
			<select
				value={field.kind}
				onchange={(e) => onFieldChange({ ...field, kind: (e.target as HTMLSelectElement).value })}
				class="h-9 rounded-md border border-input bg-background px-2 py-1 text-sm shadow-sm focus:ring-1 focus:ring-ring focus:outline-none"
				aria-label="Field type"
			>
				{#each allDescriptors().filter((d) => d.selectable !== false && (allowGroup || d.kind !== 'group')) as d (d.kind)}
					<option value={d.kind}>{d.label}</option>
				{/each}
			</select>
		{/if}
		<label class="flex items-center gap-1.5 text-sm">
			<input
				type="checkbox"
				checked={field.required}
				onchange={(e) =>
					onFieldChange({ ...field, required: (e.target as HTMLInputElement).checked })}
				class="h-4 w-4 rounded border-input accent-primary"
			/>
			Required
		</label>
		<Button type="button" variant="ghost" size="icon" onclick={onRemove} aria-label="Remove field">
			<X class="size-4" />
		</Button>
	</div>

	{@const desc = getDescriptor(field.kind)}
	{#if desc?.EditorExtras}
		{@const Extras = desc.EditorExtras}
		<Extras {field} onChange={onFieldChange} />
	{/if}
{/snippet}

<div class="space-y-3">
	<Label>Fields</Label>

	{#each items as item, i (isSection(item) ? item.id : item.key)}
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
					{#each item.fields as field, fi (field.key)}
						{@render fieldRow(
							field,
							false,
							(value) => handleSectionFieldLabelChange(i, fi, value),
							() => removeFieldFromSection(i, fi),
							(f) => handleSectionFieldChange(i, fi, f)
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
				() => removeItem(i),
				(f) => handleFieldChange(i, f)
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
