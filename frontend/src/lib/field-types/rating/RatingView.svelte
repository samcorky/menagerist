<script lang="ts">
	import { Star } from '@lucide/svelte';
	import type { JsonSchemaProperty } from '$lib/schema-types';
	import { MAX_STARS } from './rating';

	let { value, prop }: { value: unknown; prop: JsonSchemaProperty } = $props();

	const FILLED = 'fill-amber-400 text-amber-400';

	let max = $derived(prop.type === 'number' ? (prop.maximum ?? MAX_STARS) : MAX_STARS);
	let current = $derived(value === '' || value == null ? 0 : Number(value) || 0);
</script>

{#if current > 0}
	<span
		class="inline-flex items-center gap-0.5"
		role="img"
		aria-label="{current} out of {max} stars"
	>
		{#each Array.from({ length: max }, (_, i) => i + 1) as n (n)}
			<Star class="size-4 {n <= current ? FILLED : 'text-muted-foreground/40'}" />
		{/each}
	</span>
{:else}
	<span>—</span>
{/if}
