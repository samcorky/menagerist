<script lang="ts">
	import { Star } from '@lucide/svelte';
	import type { JsonSchemaProperty } from '$lib/schema-types';
	import { MAX_STARS } from './rating';
	import { filledStarClass } from './colour';

	let { value, prop, size }: { value: unknown; prop: JsonSchemaProperty; size: 'sm' | 'md' } =
		$props();

	let FILLED = $derived(filledStarClass(prop));

	let max = $derived(prop.type === 'number' ? (prop.maximum ?? MAX_STARS) : MAX_STARS);
	let current = $derived(value === '' || value == null ? 0 : Number(value) || 0);
</script>

{#if current > 0}
	<span
		class="inline-flex shrink-0 items-center"
		role="img"
		aria-label="{current} out of {max} stars"
	>
		{#each Array.from({ length: max }, (_, i) => i + 1) as n (n)}
			<Star
				class="{size === 'sm' ? 'size-3' : 'size-4'} {n <= current
					? FILLED
					: 'text-muted-foreground/40'}"
			/>
		{/each}
	</span>
{/if}
