<script lang="ts">
	import type { Snippet } from 'svelte';

	// Stands in for dialog parts in server-rendered component tests: renders the title and children.
	let {
		open = $bindable(false),
		ref = $bindable(null),
		title,
		children
	}: { open?: boolean; ref?: unknown; title?: string; children?: Snippet } = $props();
	void open;
	void ref;
</script>

{#if title}<h2>{title}</h2>{/if}
{@render children?.()}
