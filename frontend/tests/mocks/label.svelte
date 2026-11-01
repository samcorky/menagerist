<script lang="ts">
	import type { Snippet } from 'svelte';

	// Stands in for the bits-ui label, which renders nothing when server-rendered in tests.
	let { for: htmlFor, children }: { for?: string; children?: Snippet } = $props();
</script>

<label for={htmlFor}>{@render children?.()}</label>
