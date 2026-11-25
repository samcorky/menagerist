<script lang="ts">
	import ChevronRightIcon from '@lucide/svelte/icons/chevron-right';

	// An item's name, with its `crumb` (a type's parent) before it and a small muted chevron
	// between. The chevron is decoration: a screen reader hears "Memorabilia, Poster".
	let { label, crumb }: { label: string; crumb?: string } = $props();
</script>

{#if crumb}
	<span class="text-muted-foreground">{crumb}</span>
	<ChevronRightIcon
		class="mx-0.5 inline size-3 shrink-0 text-muted-foreground"
		aria-hidden="true"
	/>
	<span class="sr-only">, </span>
{/if}{label}
