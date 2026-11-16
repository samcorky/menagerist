<script lang="ts">
	import { Skeleton } from '$lib/components/ui/skeleton/index.js';

	/**
	 * Placeholder for the bordered, divided row lists on the library pages (item types,
	 * connection types, saved fields). Matches their row padding, icon tile and two text lines.
	 */
	let {
		count = 4,
		tile = false,
		description = true
	}: {
		count?: number;
		/** Reserve the leading icon tile that item type rows carry. */
		tile?: boolean;
		/** Reserve the muted second line under the name. */
		description?: boolean;
	} = $props();

	const slots = $derived(Array.from({ length: count }, (_, i) => i));
</script>

<ul data-slot="list-row-skeleton" class="divide-y rounded-xl border bg-card" aria-hidden="true">
	{#each slots as slot (slot)}
		<li class="flex items-center gap-3 px-3 py-2">
			{#if tile}
				<Skeleton class="size-8 shrink-0 rounded-lg" />
			{/if}
			<div class="min-w-0 flex-1 space-y-1">
				<Skeleton class="h-5 w-40 max-w-full rounded" />
				{#if description}
					<Skeleton class="h-4 w-64 max-w-full rounded" />
				{/if}
			</div>
			<Skeleton class="size-8 shrink-0 rounded-md" />
		</li>
	{/each}
</ul>
