<script lang="ts">
	import type { Snippet } from 'svelte';
	import { listNodeMedia } from '$lib/api/client';

	let {
		nodeId,
		class: cls = '',
		hiRes = false,
		children
	}: { nodeId: string; class?: string; hiRes?: boolean; children?: Snippet } = $props();

	const mediaPromise = $derived(
		listNodeMedia({ path: { node_id: nodeId } }).then(({ data }) => {
			const cover = data?.find((item) => item.attribute_key === 'cover');
			if (!cover) return null;
			return {
				thumb: cover.thumbnail_url ?? cover.content_url ?? null,
				full: cover.content_url ?? cover.thumbnail_url ?? null
			};
		})
	);

	let fullLoaded = $state(false);

	$effect(() => {
		void nodeId; // reactive dependency — reset when nodeId changes
		fullLoaded = false;
	});
</script>

{#await mediaPromise then cover}
	{#if cover?.thumb}
		{#if hiRes && cover.full !== cover.thumb}
			<div class="grid {cls}">
				<img
					src={cover.thumb}
					alt=""
					class="col-start-1 row-start-1 w-full object-contain transition-[filter] duration-500 {fullLoaded
						? ''
						: 'blur-sm'}"
					aria-hidden="true"
				/>
				<img
					src={cover.full}
					alt=""
					class="col-start-1 row-start-1 w-full object-contain transition-opacity duration-500 {fullLoaded
						? 'opacity-100'
						: 'opacity-0'}"
					onload={() => (fullLoaded = true)}
					loading="eager"
				/>
			</div>
		{:else}
			<img
				src={cover.full ?? cover.thumb}
				alt=""
				class="{hiRes ? 'object-contain' : 'object-cover'} {cls}"
				loading="lazy"
			/>
		{/if}
	{:else}
		{@render children?.()}
	{/if}
{:catch}
	{@render children?.()}
{/await}
