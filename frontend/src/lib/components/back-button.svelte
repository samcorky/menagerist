<script lang="ts">
	import { Button } from '$lib/components/ui/button/index.js';
	import { ChevronLeft } from '@lucide/svelte';

	let { fallback = '/' }: { fallback?: string } = $props();

	function goBack() {
		if (window.history.length > 1) {
			history.back();
		} else {
			window.location.href = fallback;
		}
	}
</script>

<Button variant="ghost" size="sm" onclick={goBack} class="-ml-2 w-fit">
	<ChevronLeft class="size-4" />
	Back
</Button>
