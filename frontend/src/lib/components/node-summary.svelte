<script lang="ts">
	import { descriptorForProp } from '$lib/field-types';
	import { summaryItems, type Surface } from '$lib/highlights';
	import type { AttributesSchema } from '$lib/schema-types';

	let {
		attributes,
		schema,
		surface,
		size = 'sm'
	}: {
		attributes: Record<string, unknown> | null | undefined;
		schema: AttributesSchema | null | undefined;
		surface: Surface;
		size?: 'sm' | 'md';
	} = $props();

	let items = $derived(summaryItems(attributes, schema, surface));
</script>

{#if items.length > 0}
	<div class="flex min-w-0 items-center gap-x-2 overflow-hidden text-xs text-muted-foreground">
		{#each items as item (item.key)}
			{@const Widget = descriptorForProp(item.prop)?.SummaryWidget}
			{#if Widget}
				<Widget value={item.value} prop={item.prop} {size} />
			{:else}
				<span class="truncate" title={item.text}>{item.text}</span>
			{/if}
		{/each}
	</div>
{/if}
