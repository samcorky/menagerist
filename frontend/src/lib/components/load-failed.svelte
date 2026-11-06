<script lang="ts">
	import { RefreshCw, WifiOff } from '@lucide/svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import { offlineController } from '$lib/offline.svelte.js';

	let { what, onretry }: { what: string; onretry: () => void } = $props();
</script>

<div
	role="alert"
	data-testid="load-failed"
	class="flex flex-col items-start gap-3 rounded-xl border border-dashed p-5"
>
	<p class="flex items-center gap-2 text-sm text-muted-foreground">
		{#if offlineController.offline}
			<WifiOff class="size-4 shrink-0" />
			You're offline, so {what} can't load.
		{:else}
			Couldn't load {what}.
		{/if}
	</p>
	<Button variant="outline" onclick={onretry}>
		<RefreshCw class="size-3.5" />
		Try again
	</Button>
</div>
