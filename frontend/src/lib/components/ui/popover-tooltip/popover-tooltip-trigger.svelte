<script lang="ts">
	import { MediaQuery } from 'svelte/reactivity';
	import type { PopoverTriggerProps, TooltipTriggerProps } from 'bits-ui';
	import * as Popover from '$lib/components/ui/popover/index.js';
	import * as Tooltip from '$lib/components/ui/tooltip/index.js';

	const isTouch = new MediaQuery('any-hover: none', false);

	let { ...restProps }: PopoverTriggerProps & TooltipTriggerProps = $props();
</script>

{#if isTouch.current}
	<Popover.Trigger {...restProps} />
{:else}
	<Tooltip.Trigger {...restProps} />
{/if}
