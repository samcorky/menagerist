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
	import {
		META_VERSION,
		archivedKeys,
		readSchemaMeta,
		withSchemaMeta,
		type SchemaMeta
	} from '$lib/schema-meta';
	import { archiveField, restoreField } from '$lib/field-archive';

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

	export function schemaToArchived(schema: AttributesSchema | null): EditorField[] {
		if (!schema) return [];
		const required = new Set(readSchemaMeta(schema).required ?? []);
		return [...archivedKeys(schema)].map((key) =>
			fieldFromProperty(key, schema.properties[key], required.has(key))
		);
	}

	export function itemsToSchema(
		items: EditorItem[],
		baseMeta: SchemaMeta,
		archived: EditorField[] = []
	): AttributesSchema | null {
		// Resolve pending keys across the whole schema so they are unique globally.
		// Archived fields are included so they keep occupying their keys.
		const visible = items.flatMap((item) => (isSection(item) ? item.fields : [item]));
		const all = [...visible, ...archived];
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

		for (const original of archived) {
			const f = resolved.get(original)!;
			if (f.key) entries.push([f.key, propertyFromField(f)]);
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
	import { setContext, untrack } from 'svelte';
	import { toast } from 'svelte-sonner';
	import { FolderOpen, Plus, Replace, X } from '@lucide/svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import {
		countNodeTypeAttributeUsage,
		purgeNodeTypeAttribute,
		countEdgeTypeAttributeUsage,
		purgeEdgeTypeAttribute
	} from '$lib/api/client';
	import { errorMessage } from '$lib/api/errors';
	import { usageLabel, purgeWarning } from '$lib/field-usage';
	import { allowedKinds, changeKind, kindChangeWarning } from '$lib/field-types/kind-changes';
	import { displayChoices, displayValue, setDisplayValue } from '$lib/field-types/display-options';
	import { SCHEMA_TYPE_CONTEXT, type SchemaTypeContext } from '$lib/schema-type-context';

	let {
		schema = $bindable<AttributesSchema | null>(null),
		typeId,
		typeKind = 'node'
	}: {
		schema?: AttributesSchema | null;
		typeId?: string;
		typeKind?: 'node' | 'edge';
	} = $props();

	setContext<SchemaTypeContext>(SCHEMA_TYPE_CONTEXT, {
		get typeId() {
			return typeId;
		},
		get kind() {
			return typeKind;
		}
	});

	// Captured once so unknown root members survive round-trips.
	const baseMeta = untrack(() => readSchemaMeta(schema));
	let items = $state<EditorItem[]>(schemaToItems(schema));
	let archived = $state<EditorField[]>(untrack(() => schemaToArchived(schema)));

	$effect(() => {
		schema = itemsToSchema(items, baseMeta, archived);
	});

	// Saved fields are archived rather than deleted so their data is kept.
	function toArchive(fields: EditorField[]): EditorField[] {
		return fields.filter((f) => !f.keyPending).map(archiveField);
	}

	function removeWithUndo(message: string, apply: () => void, archives: boolean) {
		const previousItems = $state.snapshot(items) as EditorItem[];
		const previousArchived = $state.snapshot(archived) as EditorField[];
		apply();
		if (!archives) return;
		toast(message, {
			action: {
				label: 'Undo',
				onClick: () => {
					items = previousItems;
					archived = previousArchived;
				}
			},
			duration: 5000
		});
	}

	function restoreArchived(field: EditorField) {
		if (confirmingKey === field.key) confirmingKey = null;
		archived = archived.filter((f) => f !== field);
		items = [...items, restoreField(field)];
	}

	// Usage counts per archived field key: a number, 'loading' or 'error'.
	let usage = $state<Record<string, number | 'loading' | 'error'>>({});
	let removedOpen = $state(false);
	let confirmingKey = $state<string | null>(null);
	let busyKey = $state<string | null>(null);

	async function loadUsage(key: string) {
		if (!typeId) return;
		usage[key] = 'loading';
		const result =
			typeKind === 'node'
				? await countNodeTypeAttributeUsage({ path: { node_type_id: typeId, key } })
				: await countEdgeTypeAttributeUsage({ path: { edge_type_id: typeId, key } });
		usage[key] = result.error || !result.data ? 'error' : result.data.count;
	}

	$effect(() => {
		if (!removedOpen || !typeId) return;
		for (const field of archived) {
			untrack(() => {
				if (!(field.key in usage)) void loadUsage(field.key);
			});
		}
	});

	function dropArchived(field: EditorField) {
		archived = archived.filter((f) => f !== field);
	}

	function startPurge(field: EditorField) {
		const count = usage[field.key];
		if (count === 0) {
			dropArchived(field);
			return;
		}
		if (typeof count === 'number') confirmingKey = field.key;
	}

	async function confirmPurge(field: EditorField) {
		if (!typeId) return;
		busyKey = field.key;
		const result =
			typeKind === 'node'
				? await purgeNodeTypeAttribute({ path: { node_type_id: typeId, key: field.key } })
				: await purgeEdgeTypeAttribute({ path: { edge_type_id: typeId, key: field.key } });
		busyKey = null;
		if (result.error) {
			toast.error("Couldn't delete data", { description: errorMessage(result.error) });
			return;
		}
		toast.success('Data deleted');
		confirmingKey = null;
		dropArchived(field);
	}

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
		const item = items[index];
		if (!item) return;
		const fields = isSection(item) ? item.fields : [item];
		const saved = toArchive(fields);
		removeWithUndo(
			isSection(item) ? 'Section removed' : 'Field removed',
			() => {
				archived = [...archived, ...saved];
				items = items.filter((_, i) => i !== index);
			},
			saved.length > 0
		);
	}

	function kindOptions(field: EditorField, allowGroup: boolean) {
		const listed = allDescriptors().filter(
			(d) => d.selectable !== false && (allowGroup || d.kind !== 'group')
		);
		const permitted = allowedKinds(
			field.originalKind,
			listed.map((d) => d.kind)
		);
		return listed.filter((d) => permitted.includes(d.kind));
	}

	function displayOptionsFor(field: EditorField) {
		return field.kind === 'opaque' ? [] : (getDescriptor(field.kind)?.displayOptions ?? []);
	}

	function newTextField(from: EditorField): EditorField {
		return {
			key: generateKey(),
			keyPending: true,
			label: from.label,
			kind: 'text',
			required: from.required,
			options: [],
			subFields: []
		};
	}

	function replaceItem(index: number) {
		const item = items[index];
		if (!item || isSection(item)) return;
		removeWithUndo(
			'Field replaced',
			() => {
				archived = [...archived, archiveField(item)];
				items = items.map((it, i) => (i === index ? newTextField(item) : it));
			},
			true
		);
	}

	function replaceSectionField(sectionIndex: number, fieldIndex: number) {
		const section = items[sectionIndex];
		if (!section || !isSection(section)) return;
		const old = section.fields[fieldIndex];
		if (!old) return;
		removeWithUndo(
			'Field replaced',
			() => {
				archived = [...archived, archiveField(old)];
				items = items.map((item, i) => {
					if (i !== sectionIndex || !isSection(item)) return item;
					return {
						...item,
						fields: item.fields.map((f, fi) => (fi === fieldIndex ? newTextField(old) : f))
					};
				});
			},
			true
		);
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
		const section = items[sectionIndex];
		if (!section || !isSection(section)) return;
		const saved = toArchive(section.fields.filter((_, fi) => fi === fieldIndex));
		removeWithUndo(
			'Field removed',
			() => {
				archived = [...archived, ...saved];
				items = items.map((item, i) => {
					if (i !== sectionIndex || !isSection(item)) return item;
					return { ...item, fields: item.fields.filter((_, fi) => fi !== fieldIndex) };
				});
			},
			saved.length > 0
		);
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
	onReplace: () => void,
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
				onchange={(e) => onFieldChange(changeKind(field, (e.target as HTMLSelectElement).value))}
				class="h-9 rounded-md border border-input bg-background px-2 py-1 text-sm shadow-sm focus:ring-1 focus:ring-ring focus:outline-none"
				aria-label="Field type"
			>
				{#each kindOptions(field, allowGroup) as d (d.kind)}
					<option value={d.kind}>{d.label}</option>
				{/each}
			</select>
		{/if}
		{#each displayOptionsFor(field) as option (option.key)}
			<span class="text-xs text-muted-foreground">{option.label}</span>
			<select
				value={displayValue(field, option)}
				onchange={(e) =>
					onFieldChange(setDisplayValue(field, option, (e.target as HTMLSelectElement).value))}
				class="h-9 rounded-md border border-input bg-background px-2 py-1 text-sm shadow-sm focus:ring-1 focus:ring-ring focus:outline-none"
				aria-label={option.label}
			>
				{#each displayChoices(field, option) as choice (choice.value)}
					<option value={choice.value}>{choice.label}</option>
				{/each}
			</select>
		{/each}
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
		{#if !field.keyPending && field.kind !== 'opaque'}
			<Button
				type="button"
				variant="ghost"
				size="icon"
				onclick={onReplace}
				aria-label="Replace field"
				title="Replace with a new field of a different type. The old field's values are kept until you delete them."
			>
				<Replace class="size-4" />
			</Button>
		{/if}
		<Button type="button" variant="ghost" size="icon" onclick={onRemove} aria-label="Remove field">
			<X class="size-4" />
		</Button>
	</div>
	{@const warning = kindChangeWarning(field.originalKind, field.kind)}
	{#if warning}
		<p class="text-xs text-muted-foreground" role="status">{warning}</p>
	{/if}

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
							() => replaceSectionField(i, fi),
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
				() => replaceItem(i),
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

	{#if archived.length > 0}
		<details class="pt-1" bind:open={removedOpen}>
			<summary
				class="cursor-pointer text-xs text-muted-foreground select-none hover:text-foreground"
			>
				Removed fields ({archived.length})
			</summary>
			<div class="mt-2 space-y-1">
				{#each archived as field (field.key)}
					{@const count = usage[field.key]}
					{@const busy = busyKey === field.key}
					<div class="flex flex-wrap items-center gap-2">
						<span class="flex-1 truncate text-sm text-muted-foreground">
							{field.label || 'Untitled field'}
						</span>
						{#if typeId}
							{#if count === 'loading'}
								<span class="text-xs text-muted-foreground">Checking…</span>
							{:else if typeof count === 'number'}
								<span class="text-xs text-muted-foreground">{usageLabel(count, typeKind)}</span>
							{/if}
						{/if}
						{#if confirmingKey === field.key && typeof count === 'number'}
							<span class="text-xs text-destructive">
								{purgeWarning(field.label || 'Untitled field', count, typeKind)}
							</span>
							<Button
								type="button"
								variant="ghost"
								size="sm"
								class="h-7 text-xs"
								disabled={busy}
								onclick={() => (confirmingKey = null)}
							>
								Cancel
							</Button>
							<Button
								type="button"
								variant="destructive"
								size="sm"
								class="h-7 text-xs"
								disabled={busy}
								onclick={() => confirmPurge(field)}
							>
								Delete permanently
							</Button>
						{:else}
							<Button
								type="button"
								variant="ghost"
								size="sm"
								class="h-7 text-xs"
								disabled={busyKey !== null}
								onclick={() => restoreArchived(field)}
							>
								Restore
							</Button>
							{#if typeId}
								<Button
									type="button"
									variant="ghost"
									size="sm"
									class="h-7 text-xs text-destructive hover:text-destructive"
									disabled={busyKey !== null || typeof count !== 'number'}
									onclick={() => startPurge(field)}
								>
									Delete data permanently
								</Button>
							{/if}
						{/if}
					</div>
				{/each}
			</div>
		</details>
	{/if}
</div>
