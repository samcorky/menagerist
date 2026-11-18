<script lang="ts">
	import type { Snippet } from 'svelte';
	import { listNodeMedia } from '$lib/api/client';
	import { Skeleton } from '$lib/components/ui/skeleton/index.js';

	let {
		nodeId,
		class: cls = '',
		hiRes = false,
		thumbnailUrl,
		children
	}: {
		nodeId: string;
		class?: string;
		hiRes?: boolean;
		/**
		 * The cover thumbnail a list or search already returned: a URL, or null for an item with no
		 * cover. Leave it out where the cover is not known, and the item's media is asked for instead.
		 */
		thumbnailUrl?: string | null;
		children?: Snippet;
	} = $props();

	const mediaPromise = $derived(
		thumbnailUrl !== undefined
			? null
			: listNodeMedia({ path: { node_id: nodeId } }).then(({ data }) => {
					const cover = data?.find((item) => item.attribute_key === 'cover');
					if (!cover) return null;
					return {
						thumb: cover.thumbnail_url ?? cover.content_url ?? null,
						full: cover.content_url ?? cover.thumbnail_url ?? null
					};
				})
	);

	let thumbLoaded = $state(false);
	let fullLoaded = $state(false);

	$effect(() => {
		void nodeId; // reactive dependency - reset when nodeId changes
		thumbLoaded = false;
		fullLoaded = false;
	});

	// A cached picture can finish before the page is listening for it.
	function ifLoaded(done: () => void) {
		return (img: HTMLImageElement) => {
			if (img.complete && img.naturalWidth > 0) done();
		};
	}

	// The loading state fills the space the picture will take, so nothing jumps when it arrives.
	const waitingClass = $derived(hiRes ? 'aspect-[4/3] w-full rounded-xl lg:aspect-[3/4]' : '');
</script>

{#snippet waiting(overlay: boolean)}
	<Skeleton
		data-testid="cover-loading"
		class="{overlay ? 'col-start-1 row-start-1 size-full' : cls} {waitingClass}"
	/>
{/snippet}

{#snippet picture(src: string)}
	<div class="grid {cls}">
		{#if !thumbLoaded}
			{@render waiting(true)}
		{/if}
		<img
			{src}
			alt=""
			class="col-start-1 row-start-1 {hiRes
				? 'w-full object-contain'
				: 'size-full object-cover'} transition-opacity duration-300 {thumbLoaded
				? 'opacity-100'
				: 'opacity-0'}"
			loading="lazy"
			decoding="async"
			onload={() => (thumbLoaded = true)}
			{@attach ifLoaded(() => (thumbLoaded = true))}
		/>
	</div>
{/snippet}

{#if thumbnailUrl !== undefined}
	{#if thumbnailUrl}
		{@render picture(thumbnailUrl)}
	{:else}
		{@render children?.()}
	{/if}
{:else}
	{#await mediaPromise}
		{@render waiting(false)}
	{:then cover}
		{#if cover?.thumb}
			{#if hiRes && cover.full !== cover.thumb}
				<div class="grid {cls}">
					{#if !thumbLoaded}
						{@render waiting(true)}
					{/if}
					<img
						src={cover.thumb}
						alt=""
						class="col-start-1 row-start-1 w-full object-contain transition-[filter,opacity] duration-500 {thumbLoaded
							? fullLoaded
								? 'opacity-100'
								: 'opacity-100 blur-sm'
							: 'opacity-0'}"
						aria-hidden="true"
						onload={() => (thumbLoaded = true)}
						{@attach ifLoaded(() => (thumbLoaded = true))}
					/>
					<img
						src={cover.full}
						alt=""
						class="col-start-1 row-start-1 w-full object-contain transition-opacity duration-500 {fullLoaded
							? 'opacity-100'
							: 'opacity-0'}"
						onload={() => (fullLoaded = true)}
						{@attach ifLoaded(() => (fullLoaded = true))}
						loading="eager"
					/>
				</div>
			{:else}
				{@render picture(cover.full ?? cover.thumb)}
			{/if}
		{:else}
			{@render children?.()}
		{/if}
	{:catch}
		{@render children?.()}
	{/await}
{/if}
