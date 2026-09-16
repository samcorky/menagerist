<script lang="ts">
	import { PackageSearch } from '@lucide/svelte';
	import { Button } from '$lib/components/ui/button/index.js';

	let {
		heading = 'Item not found',
		description = "This item doesn't exist, or may have been deleted.",
		backHref,
		backLabel = 'Back to collection'
	}: {
		heading?: string;
		description?: string;
		backHref?: string;
		backLabel?: string;
	} = $props();
</script>

<div class="flex flex-col items-center gap-5 py-16 text-center">
	<div class="flex size-16 items-center justify-center rounded-2xl bg-muted">
		<PackageSearch class="size-8 text-muted-foreground" />
	</div>

	<div class="space-y-1.5">
		<h2 class="font-heading text-xl font-semibold tracking-tight">{heading}</h2>
		<p class="max-w-xs text-sm text-muted-foreground">{description}</p>
	</div>

	{#if backHref}
		<Button href={backHref}>{backLabel}</Button>
	{/if}
</div>
