<script lang="ts">
	import { resolve } from '$app/paths';
	import { ChevronRight } from '@lucide/svelte';
	import * as NativeSelect from '$lib/components/ui/native-select/index.js';
	import { fetchPath, pickChoice, type ReachChoice } from '$lib/item-reach';
	import type { NodeResponse } from '$lib/api/client';

	let {
		nodeId,
		choices,
		refreshKey
	}: {
		nodeId: string;
		/** The relationships that hold this item, worded as "Inside". */
		choices: ReachChoice[];
		/** Changes when the item's connections do, to fetch again. */
		refreshKey: unknown;
	} = $props();

	let picked = $state('');
	const choice = $derived(pickChoice(choices, picked));
	let holders = $state<NodeResponse[]>([]);

	$effect(() => {
		void refreshKey;
		const slug = choice?.slug;
		if (!slug) {
			holders = [];
			return;
		}
		let current = true;
		void fetchPath(nodeId, slug).then((found) => {
			// A failed lookup just leaves the trail out: the item still shows in full.
			if (current) holders = found ?? [];
		});
		return () => {
			current = false;
		};
	});
</script>

{#if holders.length > 0}
	<nav aria-label="Where this item is" class="flex flex-wrap items-center gap-x-1 gap-y-1 text-sm">
		{#if choices.length > 1}
			<NativeSelect.Root
				class="w-auto [&_select]:h-8"
				aria-label="Show where this item is by"
				value={choice?.slug}
				onchange={(e) => (picked = e.currentTarget.value)}
			>
				{#each choices as c (c.slug)}
					<NativeSelect.Option value={c.slug}>{c.label}</NativeSelect.Option>
				{/each}
			</NativeSelect.Root>
		{:else}
			<span class="text-muted-foreground">{choice?.label}</span>
		{/if}
		{#each holders as holder, index (holder.id)}
			{#if index > 0}
				<ChevronRight class="size-3.5 text-muted-foreground" aria-hidden="true" />
			{/if}
			<a href={resolve('/items/[id]', { id: holder.id })} class="break-words underline">
				{holder.name}
			</a>
		{/each}
	</nav>
{/if}
