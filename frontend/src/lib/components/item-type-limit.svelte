<script lang="ts">
	import type { NodeTypeResponse } from '$lib/api/client';
	import MultiCombobox from '$lib/components/ui/combobox/multi-combobox.svelte';
	import type { ComboboxItem } from '$lib/components/ui/combobox/combobox';
	import TypeIcon from '$lib/components/type-icon.svelte';
	import { Label } from '$lib/components/ui/label/index.js';

	// One end of a connection type's limit: the item types it may join, or any item when empty.
	let {
		legend,
		options,
		selected = $bindable()
	}: {
		legend: string;
		options: NodeTypeResponse[];
		selected: string[];
	} = $props();

	const id = $props.id();
	const items = $derived(options.map((o) => ({ value: o.slug, label: o.label })));
	const bySlug = $derived(new Map(options.map((o) => [o.slug, o])));
	// A limit on a parent type covers its subtypes, which is worth saying once one is chosen.
	const coversSubtypes = $derived(selected.some((slug) => options.some((o) => o.parent === slug)));
</script>

<!-- A type that no longer exists has no icon or colour, so it shows the generic one. -->
{#snippet leading(item: ComboboxItem)}
	{@const type = bySlug.get(item.value)}
	<TypeIcon icon={type?.icon} colour={type?.colour} class="size-4 text-base" />
{/snippet}

<div class="space-y-1.5">
	<Label for={id}>{legend}</Label>
	<MultiCombobox
		{id}
		{items}
		{leading}
		bind:value={selected}
		placeholder="Add an item type…"
		searchPlaceholder="Search item types…"
		emptyText="No matching item types"
		unknownLabel={(slug) => `${slug} (no longer an item type)`}
		aria-describedby="{id}-hint"
	/>
	<p id="{id}-hint" class="text-xs text-muted-foreground">
		{#if selected.length === 0}
			Any item.
		{:else if coversSubtypes}
			Only these item types, and the subtypes of any that have them.
		{:else}
			Only these item types.
		{/if}
	</p>
</div>
