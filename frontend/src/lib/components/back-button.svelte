<script lang="ts">
	import { Button } from '$lib/components/ui/button/index.js';
	import { ChevronLeft } from '@lucide/svelte';
	import { sidebar } from '$lib/sidebar.svelte';

	// `peer` marks a page that is also a sidebar destination. There "Back" would only return to
	// whatever was open last, which the sidebar already offers, so it shows only where the sidebar
	// is hidden (a phone). Drill-down pages (an item, a collection) always show it.
	let { fallback = '/', peer = false }: { fallback?: string; peer?: boolean } = $props();

	function goBack() {
		if (window.history.length > 1) {
			history.back();
		} else {
			window.location.href = fallback;
		}
	}
</script>

{#if !peer || sidebar.mode === 'drawer'}
	<Button variant="ghost" size="sm" onclick={goBack} class="-ml-2 w-fit">
		<ChevronLeft class="size-4" />
		Back
	</Button>
{/if}
