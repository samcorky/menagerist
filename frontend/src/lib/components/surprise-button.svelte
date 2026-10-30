<script lang="ts">
	import { Shuffle } from '@lucide/svelte';
	import { toast } from 'svelte-sonner';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { getRandomNode } from '$lib/api/client';
	import IconButton from '$lib/components/icon-button.svelte';

	// Opens a random item, from one collection when `collection` is given, else from all of yours.
	let { collection }: { collection?: string } = $props();

	let busy = $state(false);

	async function pick() {
		busy = true;
		const result = await getRandomNode({ query: collection ? { collection } : {} });
		busy = false;
		if (result.response?.status === 404) {
			toast('Nothing to pick from yet');
			return;
		}
		if (result.error || !result.data) {
			toast.error("Couldn't pick an item");
			return;
		}
		await goto(resolve('/items/[id]', { id: result.data.id }));
	}
</script>

<IconButton label="Surprise me" variant="outline" disabled={busy} onclick={pick}>
	<Shuffle />
</IconButton>
