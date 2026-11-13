<script lang="ts">
	import { Button } from '$lib/components/ui/button/index.js';
	import { ChevronLeft } from '@lucide/svelte';
	import { goto } from '$app/navigation';
	import { canGoBackInApp, replaceNext } from '$lib/in-app-history.js';
	import { sidebar } from '$lib/sidebar.svelte';

	// `peer` marks a page that is also a sidebar destination. There "Back" would only return to
	// whatever was open last, which the sidebar already offers, so it shows only where the sidebar
	// is hidden (a phone). Drill-down pages (an item, a collection) always show it.
	let { fallback = '/', peer = false }: { fallback?: string; peer?: boolean } = $props();

	// With nothing of the app behind this page (a shortcut or link opened it) the fallback
	// replaces it, so a second Back does not return to this page.
	function goBack() {
		if (canGoBackInApp()) history.back();
		else {
			replaceNext();
			// Callers pass an already-resolved path.
			// eslint-disable-next-line svelte/no-navigation-without-resolve
			void goto(fallback, { replaceState: true });
		}
	}
</script>

{#if !peer || sidebar.mode === 'drawer'}
	<Button variant="ghost" size="sm" onclick={goBack} class="-ml-2 w-fit">
		<ChevronLeft class="size-4" />
		Back
	</Button>
{/if}
