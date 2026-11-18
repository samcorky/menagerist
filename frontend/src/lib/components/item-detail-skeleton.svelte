<script lang="ts">
	import * as Card from '$lib/components/ui/card/index.js';
	import { Skeleton } from '$lib/components/ui/skeleton/index.js';
	import type { ItemPreview } from '$lib/item-preview';

	/**
	 * Placeholder for the item page while it loads. It uses the page's own grid, so the cover,
	 * details and connections are where the real content lands. Keep the grid classes in step
	 * with items/[id]/+page.svelte. When the person came from a list, the item's title and cover
	 * thumbnail are already known and show at once.
	 */
	let { preview = null }: { preview?: ItemPreview | null } = $props();
</script>

<div
	data-testid="item-skeleton"
	class="grid w-full max-w-[96rem] items-start gap-4 lg:grid-cols-[minmax(16rem,20rem)_minmax(0,1fr)] 2xl:grid-cols-[18rem_minmax(0,1fr)_minmax(18rem,22rem)]"
	aria-hidden="true"
>
	<div data-testid="item-cover" class="lg:col-start-1 lg:row-span-2 lg:row-start-1">
		{#if preview?.cover_thumbnail_url}
			<img
				src={preview.cover_thumbnail_url}
				alt=""
				class="w-full rounded-xl border bg-card object-contain"
			/>
		{:else}
			<Skeleton class="aspect-[4/3] w-full rounded-xl lg:aspect-[3/4]" />
		{/if}
	</div>

	<div data-testid="item-main" class="min-w-0 space-y-4 lg:col-start-2 lg:row-start-1">
		<Card.Root class="overflow-hidden">
			<Card.Header class="flex flex-row items-start justify-between gap-4 space-y-0">
				<div class="min-w-0 flex-1">
					{#if preview}
						<Card.Title class="font-heading text-xl">{preview.name}</Card.Title>
					{:else}
						<Skeleton class="h-7 w-48 max-w-full rounded" />
					{/if}
					<Skeleton class="mt-2 h-9 w-full max-w-xs rounded-md" />
				</div>
				<Skeleton class="size-9 shrink-0 rounded-md" />
			</Card.Header>
			<Card.Content class="space-y-4">
				<Skeleton class="h-5 w-full rounded" />
				{#each [1, 2, 3] as row (row)}
					<div class="flex items-center gap-2">
						<Skeleton class="h-5 w-32 shrink-0 rounded" />
						<Skeleton class="h-5 flex-1 rounded" />
					</div>
				{/each}
			</Card.Content>
		</Card.Root>

		<Card.Root>
			<Card.Header>
				<Skeleton class="h-7 w-36 rounded" />
			</Card.Header>
			<Card.Content class="space-y-3">
				<Skeleton class="h-10 w-full rounded-md" />
				<Skeleton class="h-10 w-full rounded-md" />
			</Card.Content>
		</Card.Root>
	</div>
</div>
