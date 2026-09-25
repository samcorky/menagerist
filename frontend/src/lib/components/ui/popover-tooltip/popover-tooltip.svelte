<script lang="ts">
	import { MediaQuery } from 'svelte/reactivity';
	import type { PopoverRootProps, TooltipRootProps } from 'bits-ui';
	import * as Popover from '$lib/components/ui/popover/index.js';
	import * as Tooltip from '$lib/components/ui/tooltip/index.js';

	const isTouch = new MediaQuery('any-hover: none', false);

	let { open = $bindable(false), ...restProps }: PopoverRootProps & TooltipRootProps = $props();
</script>

{#if isTouch.current}
	<Popover.Root bind:open {...restProps} />
{:else}
	<Tooltip.Root bind:open {...restProps} />
{/if}
