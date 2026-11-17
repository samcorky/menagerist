<script lang="ts">
	import { RefreshCw, WifiOff } from '@lucide/svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import { offlineController, unreachableWording } from '$lib/offline.svelte.js';
	import { cn } from '$lib/utils.js';

	let {
		what,
		onretry,
		compact = false
	}: {
		what: string;
		onretry: () => void;
		/** One line with a small button, for a block inside a dashboard rather than a whole page. */
		compact?: boolean;
	} = $props();
</script>

<div
	role="alert"
	data-testid="load-failed"
	class={cn(
		'flex rounded-xl border border-dashed',
		compact ? 'items-center gap-2 p-3' : 'flex-col items-start gap-3 p-5'
	)}
>
	<p class="flex items-center gap-2 text-sm text-muted-foreground">
		{#if offlineController.offline}
			<WifiOff class="size-4 shrink-0" />
			{unreachableWording(offlineController.browserOffline).cantLoad}
			{what} can't load.
		{:else}
			Couldn't load {what}.
		{/if}
	</p>
	<Button variant="outline" size={compact ? 'sm' : 'default'} onclick={onretry}>
		<RefreshCw class="size-3.5" />
		Try again
	</Button>
</div>
