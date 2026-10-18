<script lang="ts">
	import { Terminal, Smartphone, Tablet, Monitor, CircleQuestionMark } from '@lucide/svelte';
	import type { DeviceKind } from '$lib/devices';

	let {
		kind,
		class: className = 'size-5'
	}: {
		kind: DeviceKind;
		class?: string;
	} = $props();
</script>

{#if kind === 'tool'}
	<Terminal class={className} aria-hidden="true" />
{:else if kind === 'phone'}
	<Smartphone class={className} aria-hidden="true" />
{:else if kind === 'tablet'}
	<Tablet class={className} aria-hidden="true" />
{:else if kind === 'desktop'}
	<Monitor class={className} aria-hidden="true" />
{:else}
	<CircleQuestionMark class={className} aria-hidden="true" />
{/if}
