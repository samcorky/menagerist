<script lang="ts">
	import { Badge } from '$lib/components/ui/badge/index.js';

	let { value }: { value: unknown } = $props();

	let items = $derived(Array.isArray(value) ? value.map(String) : []);
</script>

{#if items.length === 0}
	<span class="text-muted-foreground">-</span>
{:else}
	<div class="flex flex-wrap gap-1">
		{#each items as item (item)}
			<Badge variant="secondary">{item}</Badge>
		{/each}
	</div>
{/if}
