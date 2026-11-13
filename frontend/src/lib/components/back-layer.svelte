<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { registerLayer, syncLayers } from '$lib/back-layers.js';

	// Mount this inside an open sheet, dialog or full-screen overlay so the system Back gesture
	// closes it instead of leaving the page. It gives the layer one history entry while it is
	// open and removes it again when the layer closes some other way, so Back never needs
	// pressing twice. The bookkeeping lives in `back-layers.ts`.
	let { onclose }: { onclose: () => void } = $props();

	onMount(() => registerLayer(() => onclose()));

	$effect(() => {
		void page.state.layers;
		syncLayers();
	});
</script>
