<script lang="ts">
	import type { Snippet } from 'svelte';
	import { Skeleton } from '$lib/components/ui/skeleton/index.js';

	let {
		loading,
		class: className = '',
		children
	}: {
		loading: boolean;
		class?: string;
		children: Snippet;
	} = $props();
</script>

{#if loading}
	<Skeleton class={className} />
{:else}
	{@render children()}
{/if}
