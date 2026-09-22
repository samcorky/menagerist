<script lang="ts">
	import { ChevronDown, ChevronUp, Plus, X } from '@lucide/svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import ConstraintInputs from '../text/ConstraintInputs.svelte';
	import { allDescriptors } from '../registry';
	import { allowedKinds, changeKind } from '../kind-changes';
	import type { EditorField, EditorSubField } from '$lib/schema-types';

	let {
		field,
		onChange
	}: {
		field: EditorField;
		onChange: (f: EditorField) => void;
	} = $props();

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
				{ key: generateKey(), label: '', kind: 'text', keyPending: true }
			]
		});
	}

	function moveSubField(i: number, direction: -1 | 1) {
		const j = i + direction;
		const subFields = [...field.subFields];
		[subFields[i], subFields[j]] = [subFields[j], subFields[i]];
		onChange({ ...field, subFields });
	}

	function removeSubField(i: number) {
		onChange({ ...field, subFields: field.subFields.filter((_, si) => si !== i) });
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
					<select
						value={sf.kind}
						onchange={(e) => updateSubFieldKind(si, (e.target as HTMLSelectElement).value)}
						class="h-9 rounded-md border border-input bg-background px-2 py-1 text-sm shadow-sm focus:ring-1 focus:ring-ring focus:outline-none"
						aria-label="Sub-field type"
					>
						{#each kindOptions(sf) as d (d.kind)}
							<option value={d.kind}>{d.label}</option>
						{/each}
					</select>
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
					onclick={() => removeSubField(si)}
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
		</div>
	{/each}
	<Button type="button" variant="outline" size="sm" onclick={addSubField}>
		<Plus class="size-4" />
		Add sub-field
	</Button>
</div>
