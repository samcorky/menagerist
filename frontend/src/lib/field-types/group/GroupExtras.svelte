<script lang="ts">
	import { ChevronDown, ChevronUp, Plus, X } from '@lucide/svelte';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { NativeSelect, NativeSelectOption } from '$lib/components/ui/native-select/index.js';
	import { getContext } from 'svelte';
	import ConstraintInputs from '../text/ConstraintInputs.svelte';
	import { allDescriptors } from '../registry';
	import { allowedKinds, changeKind } from '../kind-changes';
	import type { EditorField, EditorSubField } from '$lib/schema-types';
	import { countEdgeTypeAttributeUsage, countNodeTypeAttributeUsage } from '$lib/api/client';
	import { optionRemovalWarning, purgeWarning } from '$lib/field-usage';
	import { SCHEMA_TYPE_CONTEXT, type SchemaTypeContext } from '$lib/schema-type-context';

	let {
		field,
		onChange
	}: {
		field: EditorField;
		onChange: (f: EditorField) => void;
	} = $props();

	const ctx = getContext<SchemaTypeContext | undefined>(SCHEMA_TYPE_CONTEXT);

	// Advisory warning after removing a choice column's option, keyed by sub-field key.
	let optionRemovalWarnings = $state<Record<string, string | null>>({});
	let removalRequests: Record<string, number> = {};

	// "Add option…" draft text for each choice column, keyed by sub-field key.
	let optionDrafts = $state<Record<string, string>>({});

	// Column removal confirmation: which index is pending, and at what usage count.
	let pendingRemoval = $state<{ index: number; count: number } | null>(null);

	// Exclude group itself and types marked as sub-field-ineligible.
	let subFieldKinds = $derived(
		allDescriptors().filter(
			(d) => d.selectable !== false && d.canBeSubField !== false && d.kind !== 'group'
		)
	);

	function kindOptions(sf: EditorSubField) {
		const permitted = allowedKinds(
			sf.originalKind,
			subFieldKinds.map((k) => k.kind)
		);
		return subFieldKinds.filter((d) => permitted.includes(d.kind));
	}

	function generateKey(): string {
		return typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
			? crypto.randomUUID()
			: `${Date.now()}-${Math.random().toString(16).slice(2)}`;
	}

	function addSubField() {
		onChange({
			...field,
			subFields: [
				...field.subFields,
				{ key: generateKey(), label: '', kind: 'text', keyPending: true, options: [] }
			]
		});
	}

	function moveSubField(i: number, direction: -1 | 1) {
		const j = i + direction;
		const subFields = [...field.subFields];
		[subFields[i], subFields[j]] = [subFields[j], subFields[i]];
		onChange({ ...field, subFields });
	}

	function removeSubFieldAt(i: number) {
		onChange({ ...field, subFields: field.subFields.filter((_, si) => si !== i) });
	}

	/** In-use count for a sub-field, or null if it can't (or needn't) be checked. Advisory only. */
	async function subFieldUsageCount(sf: EditorSubField): Promise<number | null> {
		const typeId = ctx?.typeId;
		if (!ctx || !typeId || field.keyPending || sf.keyPending) return null;
		try {
			const result =
				ctx.kind === 'node'
					? await countNodeTypeAttributeUsage({
							path: { node_type_id: typeId, key: field.key },
							query: { sub_key: sf.key }
						})
					: await countEdgeTypeAttributeUsage({
							path: { edge_type_id: typeId, key: field.key },
							query: { sub_key: sf.key }
						});
			return result.data?.count ?? 0;
		} catch {
			return null;
		}
	}

	async function requestRemoveSubField(i: number) {
		const sf = field.subFields[i];
		const count = await subFieldUsageCount(sf);
		if (!count) {
			removeSubFieldAt(i);
			return;
		}
		pendingRemoval = { index: i, count };
	}

	function confirmRemoveSubField() {
		if (!pendingRemoval) return;
		removeSubFieldAt(pendingRemoval.index);
		pendingRemoval = null;
	}

	function cancelRemoveSubField() {
		pendingRemoval = null;
	}

	function updateSubFieldLabel(i: number, label: string) {
		onChange({
			...field,
			subFields: field.subFields.map((sf, si) => (si === i ? { ...sf, label } : sf))
		});
	}

	function updateSubFieldConfig(i: number, config: Record<string, unknown>) {
		onChange({
			...field,
			subFields: field.subFields.map((sf, si) => (si === i ? { ...sf, config } : sf))
		});
	}

	function updateSubFieldKind(i: number, kind: string) {
		onChange({
			...field,
			subFields: field.subFields.map((sf, si) => (si === i ? changeKind(sf, kind) : sf))
		});
	}

	function updateSubFieldOptions(i: number, options: string[]) {
		onChange({
			...field,
			subFields: field.subFields.map((sf, si) => (si === i ? { ...sf, options } : sf))
		});
	}

	function addSubFieldOption(i: number) {
		const sf = field.subFields[i];
		const trimmed = (optionDrafts[sf.key] ?? '').trim();
		const options = sf.options ?? [];
		optionDrafts = { ...optionDrafts, [sf.key]: '' };
		if (!trimmed || options.includes(trimmed)) return;
		optionRemovalWarnings = { ...optionRemovalWarnings, [sf.key]: null };
		updateSubFieldOptions(i, [...options, trimmed]);
	}

	/** In-use warning for one removed option, or null. Advisory only; failures are ignored. */
	async function optionUsageWarning(sf: EditorSubField, opt: string): Promise<string | null> {
		const typeId = ctx?.typeId;
		if (!ctx || !typeId || field.keyPending || sf.keyPending) return null;
		try {
			const result =
				ctx.kind === 'node'
					? await countNodeTypeAttributeUsage({
							path: { node_type_id: typeId, key: field.key },
							query: { sub_key: sf.key, value: opt }
						})
					: await countEdgeTypeAttributeUsage({
							path: { edge_type_id: typeId, key: field.key },
							query: { sub_key: sf.key, value: opt }
						});
			const count = result.data?.count ?? 0;
			return count > 0 ? optionRemovalWarning(opt, count, ctx.kind) : null;
		} catch {
			return null;
		}
	}

	async function removeSubFieldOption(i: number, opt: string) {
		const sf = field.subFields[i];
		const request = (removalRequests[sf.key] ?? 0) + 1;
		removalRequests[sf.key] = request;
		optionRemovalWarnings = { ...optionRemovalWarnings, [sf.key]: null };
		updateSubFieldOptions(
			i,
			(sf.options ?? []).filter((o) => o !== opt)
		);
		const warning = await optionUsageWarning(sf, opt);
		if (removalRequests[sf.key] === request && warning) {
			optionRemovalWarnings = { ...optionRemovalWarnings, [sf.key]: warning };
		}
	}
</script>

<div class="ml-6 space-y-2 border-l border-input pl-4">
	{#each field.subFields as sf, si (sf.key)}
		<div class="space-y-1">
			<div class="flex flex-wrap items-center gap-2">
				<Input
					value={sf.label}
					placeholder="Label"
					class="w-40"
					aria-label="Sub-field label"
					oninput={(e) => updateSubFieldLabel(si, (e.target as HTMLInputElement).value)}
				/>
				{#if sf.kind === 'opaque'}
					<span class="rounded border border-input px-1.5 text-xs text-muted-foreground"
						>custom</span
					>
				{:else}
					<NativeSelect
						value={sf.kind}
						onchange={(e) => updateSubFieldKind(si, (e.target as HTMLSelectElement).value)}
						aria-label="Sub-field type"
					>
						{#each kindOptions(sf) as d (d.kind)}
							<NativeSelectOption value={d.kind}>{d.label}</NativeSelectOption>
						{/each}
					</NativeSelect>
				{/if}
				<Button
					type="button"
					variant="ghost"
					size="icon"
					disabled={si === 0}
					onclick={() => moveSubField(si, -1)}
					aria-label="Move {sf.label || 'column'} earlier"
				>
					<ChevronUp class="size-4" />
				</Button>
				<Button
					type="button"
					variant="ghost"
					size="icon"
					disabled={si === field.subFields.length - 1}
					onclick={() => moveSubField(si, 1)}
					aria-label="Move {sf.label || 'column'} later"
				>
					<ChevronDown class="size-4" />
				</Button>
				<Button
					type="button"
					variant="ghost"
					size="icon"
					onclick={() => requestRemoveSubField(si)}
					aria-label="Remove sub-field"
				>
					<X class="size-4" />
				</Button>
			</div>
			{#if sf.kind === 'text'}
				<div class="ml-2">
					<ConstraintInputs
						config={sf.config}
						idPrefix="sub-{sf.key}"
						onChange={(config) => updateSubFieldConfig(si, config)}
					/>
				</div>
			{/if}
			{#if sf.kind === 'choice'}
				<div class="ml-2 space-y-1.5">
					{#if (sf.options ?? []).length > 0}
						<ul class="flex flex-wrap gap-1">
							{#each sf.options ?? [] as opt (opt)}
								<li>
									<Badge variant="secondary" class="pr-1">
										<span class="max-w-32 truncate" title={opt}>{opt}</span>
										<button
											type="button"
											onclick={() => removeSubFieldOption(si, opt)}
											aria-label="Remove option {opt}"
											class="relative ml-1 rounded-full p-0.5 after:absolute after:-inset-2 after:content-[''] hover:bg-foreground/10 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
										>
											<X class="size-3" />
										</button>
									</Badge>
								</li>
							{/each}
						</ul>
					{/if}
					<div class="flex gap-1.5">
						<Input
							value={optionDrafts[sf.key] ?? ''}
							oninput={(e) =>
								(optionDrafts = {
									...optionDrafts,
									[sf.key]: (e.target as HTMLInputElement).value
								})}
							placeholder="Add option…"
							class="h-7 w-36 text-xs"
							onkeydown={(e) => {
								if (e.key === 'Enter') {
									e.preventDefault();
									addSubFieldOption(si);
								}
							}}
						/>
						<Button
							type="button"
							variant="ghost"
							size="sm"
							class="h-7 px-2"
							onclick={() => addSubFieldOption(si)}
						>
							<Plus class="size-3" />
						</Button>
					</div>
					{#if optionRemovalWarnings[sf.key]}
						<p class="text-xs text-muted-foreground" role="status">
							{optionRemovalWarnings[sf.key]}
						</p>
					{/if}
				</div>
			{/if}
			{#if pendingRemoval?.index === si}
				<div class="ml-2 flex flex-wrap items-center gap-2">
					<p class="text-xs text-muted-foreground" role="status">
						{purgeWarning(sf.label || 'Untitled column', pendingRemoval.count, ctx?.kind ?? 'node')}
					</p>
					<Button type="button" variant="destructive" size="sm" onclick={confirmRemoveSubField}>
						Delete
					</Button>
					<Button type="button" variant="ghost" size="sm" onclick={cancelRemoveSubField}>
						Cancel
					</Button>
				</div>
			{/if}
		</div>
	{/each}
	<Button type="button" variant="outline" size="sm" onclick={addSubField}>
		<Plus class="size-4" />
		Add sub-field
	</Button>
</div>
