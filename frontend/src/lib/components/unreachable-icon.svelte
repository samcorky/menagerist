<script lang="ts">
	import { ServerOff, WifiOff } from '@lucide/svelte';
	import { offlineController } from '$lib/offline.svelte.js';

	// The icon beside "You're offline" or "Can't reach Menagerist". A browser with no network gets
	// the broken-wifi mark; one that is online but cannot reach the server gets the server mark,
	// since the connection itself is fine. Matches `unreachableWording`.
	let { class: className }: { class?: string } = $props();
</script>

{#if offlineController.browserOffline}
	<WifiOff class={className} data-icon="wifi-off" />
{:else}
	<ServerOff class={className} data-icon="server-off" />
{/if}
