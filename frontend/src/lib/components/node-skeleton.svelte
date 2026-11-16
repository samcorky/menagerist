<script lang="ts">
	import * as Item from '$lib/components/ui/item/index.js';
	import { Skeleton } from '$lib/components/ui/skeleton/index.js';

	/**
	 * Placeholder for a page of items. Mirrors NodeGridCard and NodeCard (same grid, card
	 * aspect ratio and row height) so real content replaces it without shifting.
	 */
	let { view, count = 8 }: { view: 'grid' | 'list'; count?: number } = $props();

	const slots = $derived(Array.from({ length: count }, (_, i) => i));
</script>

{#if view === 'grid'}
	<div
		data-slot="node-skeleton"
		class="grid grid-cols-[repeat(auto-fill,minmax(11rem,1fr))] gap-2"
		aria-hidden="true"
	>
		{#each slots as slot (slot)}
			<div class="flex aspect-[3/4] flex-col overflow-hidden rounded-xl border bg-muted/30">
				<Skeleton class="min-h-0 flex-1 rounded-none" />
				<div class="space-y-1.5 border-t bg-background/80 px-2.5 py-2">
					<Skeleton class="h-3.5 w-3/4 rounded" />
					<Skeleton class="h-3 w-1/2 rounded" />
				</div>
			</div>
		{/each}
	</div>
{:else}
	<Item.Group data-slot="node-skeleton" class="max-w-5xl" aria-hidden="true">
		{#each slots as slot (slot)}
			<Item.Root variant="outline">
				<Skeleton class="size-12 shrink-0 rounded-lg" />
				<Item.Content class="min-w-0 gap-1.5">
					<Skeleton class="h-5 w-48 max-w-full rounded" />
					<Skeleton class="h-4 w-72 max-w-full rounded" />
				</Item.Content>
				<Item.Actions>
					<Skeleton class="h-5 w-16 rounded-full" />
				</Item.Actions>
			</Item.Root>
		{/each}
	</Item.Group>
{/if}
