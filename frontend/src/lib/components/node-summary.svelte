<script lang="ts">
	import { coreForProp } from '$lib/field-types';
	import { summaryItems, type Surface } from '$lib/highlights';
	import type { AttributesSchema } from '$lib/schema-types';
	import * as Tooltip from '$lib/components/ui/popover-tooltip/index.js';

	let {
		attributes,
		schema,
		surface,
		size = 'sm',
		wrap = false
	}: {
		attributes: Record<string, unknown> | null | undefined;
		schema: AttributesSchema | null | undefined;
		surface: Surface;
		size?: 'sm' | 'md';
		/** Let values flow onto further lines instead of truncating on one. */
		wrap?: boolean;
	} = $props();

	let items = $derived(summaryItems(attributes, schema, surface));
</script>

{#if items.length > 0}
	<div
		class={[
			'flex min-w-0 items-center gap-x-2 text-xs text-muted-foreground',
			wrap ? 'flex-wrap gap-y-0.5' : 'overflow-hidden'
		]}
	>
		{#each items as item (item.key)}
			{@const Widget = coreForProp(item.prop)?.SummaryWidget}
			<Tooltip.Root>
				<Tooltip.Trigger>
					{#snippet child({ props })}
						{#if Widget}
							<span {...props} tabindex="-1" class="inline-flex min-w-0 shrink-0 items-center">
								<Widget value={item.value} prop={item.prop} {size} />
							</span>
						{:else}
							<span {...props} tabindex="-1" class={wrap ? 'break-words' : 'truncate'}
								>{item.text}</span
							>
						{/if}
					{/snippet}
				</Tooltip.Trigger>
				<Tooltip.Content>{item.label}: {item.text}</Tooltip.Content>
			</Tooltip.Root>
		{/each}
	</div>
{/if}
