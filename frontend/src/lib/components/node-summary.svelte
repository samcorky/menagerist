<script lang="ts">
	import { descriptorForProp } from '$lib/field-types';
	import { summaryItems, type Surface } from '$lib/highlights';
	import type { AttributesSchema } from '$lib/schema-types';
	import * as Tooltip from '$lib/components/ui/tooltip/index.js';

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
			<Tooltip.Root>
				<Tooltip.Trigger>
					{#snippet child({ props })}
						{#if Widget}
							<span {...props} tabindex="-1" class="inline-flex min-w-0 shrink-0 items-center">
								<Widget value={item.value} prop={item.prop} {size} />
							</span>
						{:else}
							<span {...props} tabindex="-1" class="truncate">{item.text}</span>
						{/if}
					{/snippet}
				</Tooltip.Trigger>
				<Tooltip.Content>{item.label}: {item.text}</Tooltip.Content>
			</Tooltip.Root>
		{/each}
	</div>
{/if}
