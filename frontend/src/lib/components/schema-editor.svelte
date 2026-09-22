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
		withHighlights,
		withSchemaMeta,
		type HighlightList,
		type SchemaMeta
	} from '$lib/schema-meta';
	import { archiveField, restoreField } from '$lib/field-archive';
	import { highlightRanks, maxHighlights, normaliseHighlights } from '$lib/highlights';

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

	export function schemaToItems(
		schema: AttributesSchema | null,
		list: HighlightList = 'card'
	): EditorItem[] {
		if (!schema) return [];
		const required = new Set(readSchemaMeta(schema).required ?? []);
		const layout = normalise(readSchemaMeta(schema).layout, schema.properties);
		const ranks = highlightRanks(schema, list);
		const load = (key: string): EditorField => {
			const field = fieldFromProperty(key, schema.properties[key], required.has(key));
			const rank = ranks.get(key);
			return rank === undefined ? field : { ...field, highlight: rank };
		};
		return layout.flatMap((layoutItem): EditorItem[] => {
			if (isSectionItem(layoutItem)) {
				return [
					{
						_section: true,
						id: layoutItem.id,
						sectionLabel: layoutItem.section,
						fields: layoutItem.items
							.filter((i) => i.key in schema.properties)
							.map((i) => load(i.key))
					}
				];
			}
			if (!(layoutItem.key in schema.properties)) return [];
			return [load(layoutItem.key)];
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
		archived: EditorField[] = [],
		list: HighlightList = 'card'
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
		const card = visible
			.filter((f) => f.highlight !== undefined)
			.sort((a, b) => a.highlight! - b.highlight!)
			.map((f) => ({ key: resolved.get(f)!.key }));
		const withMeta = withSchemaMeta(base, {
			...baseMeta,
			version: META_VERSION,
			layout,
			required
		});
		return withHighlights(
			withMeta,
			normaliseHighlights(card, base.properties, maxHighlights(list)),
			list
		);
	}
</script>

<script lang="ts">
	import { setContext, untrack } from 'svelte';
	import { toast } from 'svelte-sonner';
	import {
		BookmarkPlus,
		ChevronDown,
		ChevronUp,
		FolderOpen,
		Pin,
		Plus,
		Replace,
		X
	} from '@lucide/svelte';
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
	import { canHighlightMore, movedRanks, toggledRanks } from '$lib/highlights';
	import {
		definitionToField,
		fieldToDefinition,
		type FieldDefinition,
		type Preset
	} from '$lib/presets';
	import SavePresetDialog from '$lib/components/save-preset-dialog.svelte';
	import PresetPickerDialog from '$lib/components/preset-picker-dialog.svelte';

	let {
		schema = $bindable<AttributesSchema | null>(null),
		typeId,
		typeKind = 'node',
		highlights = false,
		highlightList = 'card'
	}: {
		schema?: AttributesSchema | null;
		typeId?: string;
		typeKind?: 'node' | 'edge';
		highlights?: boolean;
		highlightList?: HighlightList;
	} = $props();

	let maxShown = $derived(maxHighlights(highlightList));
	let onConnections = $derived(highlightList === 'connection');

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
	let items = $state<EditorItem[]>(untrack(() => schemaToItems(schema, highlightList)));
	let archived = $state<EditorField[]>(untrack(() => schemaToArchived(schema)));

	$effect(() => {
		schema = itemsToSchema(items, baseMeta, archived, highlightList);
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
		items = [...items, { ...restoreField(field), highlight: undefined }];
	}

	// Visible fields in display order, sections flattened; archived and sub-fields excluded.
	let flatFields = $derived(items.flatMap((item) => (isSection(item) ? item.fields : [item])));
	// Highlight ranks per flattened field, renumbered so removals leave no gaps.
	let ranks = $derived.by(() => {
		const raw = flatFields.map((f) => f.highlight);
		const order = raw.filter((r): r is number => r !== undefined).sort((a, b) => a - b);
		return raw.map((r) => (r === undefined ? undefined : order.indexOf(r) + 1));
	});
	let atHighlightLimit = $derived(!canHighlightMore(ranks, maxShown));
	let highlightedFields = $derived(
		flatFields
			.map((field, index) => ({ field, index, rank: ranks[index] }))
			.filter((e) => e.rank !== undefined)
			.sort((a, b) => a.rank! - b.rank!)
	);

	function isHighlightableField(field: EditorField): boolean {
		return field.kind !== 'opaque' && getDescriptor(field.kind)?.highlightable === true;
	}

	function applyRanks(next: (number | undefined)[]) {
		let n = 0;
		const rerank = (f: EditorField): EditorField => ({ ...f, highlight: next[n++] });
		items = items.map((item) =>
			isSection(item) ? { ...item, fields: item.fields.map(rerank) } : rerank(item)
		);
	}

	function toggleHighlight(field: EditorField) {
		const index = flatFields.findIndex((f) => f.key === field.key);
		if (index !== -1) applyRanks(toggledRanks(ranks, index, maxShown));
	}

	function moveHighlight(index: number, direction: -1 | 1) {
		applyRanks(movedRanks(ranks, index, direction));
	}

	function handleKindChange(field: EditorField, kind: string): EditorField {
		const next = changeKind(field, kind);
		return isHighlightableField(next) ? next : { ...next, highlight: undefined };
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

	// Field currently targeted by the "save for reuse" dialog.
	let savingField = $state<EditorField | null>(null);
	let pickerOpen = $state(false);

	function addFieldFromPreset(preset: Preset) {
		const field = definitionToField(preset.definition as FieldDefinition, {
			preset: preset.id,
			version: preset.version
		});
		items = [...items, field];
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
				onchange={(e) =>
					onFieldChange(handleKindChange(field, (e.target as HTMLSelectElement).value))}
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
		{#if highlights && isHighlightableField(field)}
			{@const pinned = field.highlight !== undefined}
			{@const target = onConnections ? 'connection' : 'card'}
			<Button
				type="button"
				variant="ghost"
				size="icon"
				aria-pressed={pinned}
				aria-label={pinned ? `Stop showing on ${target}` : `Show on ${target}`}
				title={pinned ? `Stop showing on ${target}` : `Show on ${target}`}
				disabled={!pinned && atHighlightLimit}
				class={pinned ? 'text-primary' : 'text-muted-foreground'}
				onclick={() => toggleHighlight(field)}
			>
				<Pin class="size-4 {pinned ? 'fill-current' : ''}" />
			</Button>
		{/if}
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
		{#if field.kind !== 'opaque'}
			<Button
				type="button"
				variant="ghost"
				size="icon"
				onclick={() => (savingField = field)}
				aria-label="Save field for reuse"
				title="Save this field for reuse"
			>
				<BookmarkPlus class="size-4" />
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
		<Button type="button" variant="ghost" size="sm" onclick={() => (pickerOpen = true)}>
			<BookmarkPlus class="size-4" />
			Add from saved fields…
		</Button>
	</div>

	{#if highlights}
		{#if atHighlightLimit}
			<p class="text-xs text-muted-foreground">
				{#if onConnections}
					You can show up to {maxShown} details on a connection row.
				{:else}
					You can show up to {maxShown} fields on a card.
				{/if}
			</p>
		{/if}
		{#if highlightedFields.length > 0}
			<div class="space-y-1">
				<Label>{onConnections ? 'Shown on connections' : 'Shown on cards'}</Label>
				<ol class="space-y-0.5">
					{#each highlightedFields as entry, position (entry.field.key)}
						{@const label = entry.field.label || 'Untitled field'}
						<li class="flex items-center gap-1 text-sm">
							<span class="w-4 text-xs text-muted-foreground">{position + 1}.</span>
							<span class="min-w-0 flex-1 truncate">{label}</span>
							<Button
								type="button"
								variant="ghost"
								size="icon"
								class="size-7"
								disabled={position === 0}
								onclick={() => moveHighlight(entry.index, -1)}
								aria-label="Move {label} earlier"
							>
								<ChevronUp class="size-4" />
							</Button>
							<Button
								type="button"
								variant="ghost"
								size="icon"
								class="size-7"
								disabled={position === highlightedFields.length - 1}
								onclick={() => moveHighlight(entry.index, 1)}
								aria-label="Move {label} later"
							>
								<ChevronDown class="size-4" />
							</Button>
						</li>
					{/each}
				</ol>
			</div>
		{/if}
	{/if}

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

{#if savingField}
	<SavePresetDialog
		open={savingField !== null}
		kind="field"
		definition={fieldToDefinition(savingField)}
		onOpenChange={(v) => {
			if (!v) savingField = null;
		}}
		onSaved={() => {}}
	/>
{/if}

<PresetPickerDialog
	open={pickerOpen}
	kind="field"
	title="Add from saved fields"
	onOpenChange={(v) => (pickerOpen = v)}
	onPick={addFieldFromPreset}
/>
