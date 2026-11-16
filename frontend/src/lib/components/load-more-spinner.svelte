<script lang="ts">
	import { Spinner } from '$lib/components/ui/spinner/index.js';

	/**
	 * Shown at the end of a list while the next page loads. The first page uses a skeleton
	 * instead, so this stays hidden until there are rows (§13a: never both together).
	 */
	let { loading, hasRows }: { loading: boolean; hasRows: boolean } = $props();
</script>

{#if loading && hasRows}
	<Spinner class="size-5 text-muted-foreground" aria-label="Loading more" />
{/if}
