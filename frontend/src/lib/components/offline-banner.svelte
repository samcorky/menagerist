<script lang="ts">
	import { RefreshCw, WifiOff } from '@lucide/svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import { offlineController } from '$lib/offline.svelte.js';
</script>

{#if offlineController.offline}
	<div
		role="status"
		data-testid="offline-banner"
		class="flex flex-wrap items-center justify-between gap-2 border-b bg-muted px-4 py-2 text-sm"
	>
		<p class="flex items-center gap-2">
			<WifiOff class="size-4 shrink-0 text-muted-foreground" />
			You're offline. Some things may not load.
		</p>
		<Button variant="outline" size="sm" onclick={() => offlineController.retry()}>
			<RefreshCw class="size-3.5" />
			Retry
		</Button>
	</div>
{/if}
