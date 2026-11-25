<script lang="ts">
	import type { NodeTypeResponse } from '$lib/api/client';
	import MultiCombobox from '$lib/components/ui/combobox/multi-combobox.svelte';
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
</script>

<div class="space-y-1.5">
	<Label for={id}>{legend}</Label>
	<MultiCombobox
		{id}
		{items}
		bind:value={selected}
		placeholder="Add an item type…"
		searchPlaceholder="Search item types…"
		emptyText="No matching item types"
		unknownLabel={(slug) => `${slug} (no longer an item type)`}
		aria-describedby="{id}-hint"
	/>
	<p id="{id}-hint" class="text-xs text-muted-foreground">
		{selected.length === 0 ? 'Any item.' : 'Only these item types.'}
	</p>
</div>
