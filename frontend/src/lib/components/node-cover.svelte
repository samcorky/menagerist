<script lang="ts">
	import type { Snippet } from 'svelte';
	import { listNodeMedia } from '$lib/api/client';

	let {
		nodeId,
		class: cls = '',
		children
	}: { nodeId: string; class?: string; children?: Snippet } = $props();

	const mediaPromise = $derived(
		listNodeMedia({ path: { node_id: nodeId } }).then(({ data }) => {
			const cover = data?.find((item) => item.attribute_key === 'cover');
			return cover?.thumbnail_url ?? cover?.content_url ?? null;
		})
	);
</script>

{#await mediaPromise then coverUrl}
	{#if coverUrl}
		<img src={coverUrl} alt="" class="h-full w-full object-cover {cls}" loading="lazy" />
	{:else}
		{@render children?.()}
	{/if}
{:catch}
	{@render children?.()}
{/await}
