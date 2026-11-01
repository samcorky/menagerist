<script lang="ts">
	import { MediaQuery } from 'svelte/reactivity';
	import type { PopoverContentProps, TooltipContentProps } from 'bits-ui';
	import * as Popover from '$lib/components/ui/popover/index.js';
	import * as Tooltip from '$lib/components/ui/tooltip/index.js';
	import { cn } from '$lib/utils.js';

	const isTouch = new MediaQuery('any-hover: none', false);

	let {
		class: className,
		...restProps
	}: { class?: string } & PopoverContentProps & TooltipContentProps = $props();
</script>

{#if isTouch.current}
	<Popover.Content class={cn('w-auto px-3 py-1.5 text-sm', className)} side="top" {...restProps} />
{:else}
	<Tooltip.Content class={cn('font-medium', className)} {...restProps} />
{/if}
