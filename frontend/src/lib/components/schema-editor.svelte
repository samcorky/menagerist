<script lang="ts" module>
	import type { AttributesSchema, EditorField } from '$lib/schema-types';
</script>

<script lang="ts">
	import { setContext, untrack } from 'svelte';
	import { toast } from 'svelte-sonner';
	import {
		BookmarkPlus,
		ChevronDown,
		ChevronUp,
		FolderOpen,
		MoreVertical,
		Pin,
		Plus,
		Replace,
		X
	} from '@lucide/svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu/index.js';
	import {
		countNodeTypeAttributeUsage,
		purgeNodeTypeAttribute,
		countEdgeTypeAttributeUsage,
		purgeEdgeTypeAttribute
	} from '$lib/api/client';
	import { errorMessage } from '$lib/api/errors';
	import { usageLabel, purgeWarning } from '$lib/field-usage';
	import { getDescriptor } from '$lib/field-types';
	import { SCHEMA_TYPE_CONTEXT, type SchemaTypeContext } from '$lib/schema-type-context';
	import { readSchemaMeta, type HighlightList } from '$lib/schema-meta';
	import {
		isSection,
		schemaToItems,
		schemaToArchived,
		itemsToSchema,
		type EditorItem
	} from '$lib/schema-editor-items';
	import { archiveField, restoreField } from '$lib/field-archive';
	import { canHighlightMore, maxHighlights, movedRanks, toggledRanks } from '$lib/highlights';
	import {
		definitionToField,
		fieldToDefinition,
		type FieldDefinition,
		type Preset
	} from '$lib/presets';
	import SavePresetDialog from '$lib/components/save-preset-dialog.svelte';
	import PresetPickerDialog from '$lib/components/preset-picker-dialog.svelte';
	import FieldKindRow from '$lib/components/field-kind-row.svelte';

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

	// FieldKindRow reports any field change (kind, display option, required) through one
	// callback; only an actual kind change can make a field non-highlightable, so only
	// clear the highlight when the kind itself changed.
	function handleFieldRowChange(field: EditorField, next: EditorField): EditorField {
		if (next.kind !== field.kind && !isHighlightableField(next)) {
			if (field.highlight !== undefined) {
				const label = field.label || 'Untitled field';
				const kindLabel = getDescriptor(next.kind)?.label.toLowerCase();
				toast(onConnections ? 'No longer shown on connections' : 'No longer shown on cards', {
					description: `"${label}" can no longer be highlighted as a ${kindLabel} field.`
				});
			}
			return { ...next, highlight: undefined };
		}
		return next;
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
	<div class="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
		<div class="min-w-0 sm:flex-1">
			<FieldKindRow
				{field}
				{allowGroup}
				{onLabelChange}
				onFieldChange={(next) => onFieldChange(handleFieldRowChange(field, next))}
			/>
		</div>
		<div class="flex items-center justify-end gap-1 sm:justify-start">
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
			{#if field.kind !== 'opaque'}
				<DropdownMenu.Root>
					<DropdownMenu.Trigger>
						{#snippet child({ props })}
							<Button
								{...props}
								type="button"
								variant="ghost"
								size="icon"
								aria-label="More field actions"
							>
								<MoreVertical class="size-4" />
							</Button>
						{/snippet}
					</DropdownMenu.Trigger>
					<DropdownMenu.Content align="end">
						{#if !field.keyPending}
							<DropdownMenu.Item onSelect={onReplace}>
								<Replace class="size-4" />
								Replace field
							</DropdownMenu.Item>
						{/if}
						<DropdownMenu.Item onSelect={() => (savingField = field)}>
							<BookmarkPlus class="size-4" />
							Save field for reuse
						</DropdownMenu.Item>
					</DropdownMenu.Content>
				</DropdownMenu.Root>
			{/if}
			<Button
				type="button"
				variant="ghost"
				size="icon"
				onclick={onRemove}
				aria-label="Remove field"
			>
				<X class="size-4" />
			</Button>
		</div>
	</div>
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
						class="h-8 min-w-0 flex-1 text-sm font-medium sm:w-44 sm:flex-none"
						aria-label="Section name"
						oninput={(e) => handleSectionLabelChange(i, (e.target as HTMLInputElement).value)}
					/>
					<span class="hidden text-xs text-muted-foreground sm:inline">Section</span>
					<Button
						type="button"
						variant="ghost"
						size="icon"
						class="ml-auto"
						onclick={() => removeItem(i)}
						aria-label="Remove section"
					>
						<X class="size-4" />
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
