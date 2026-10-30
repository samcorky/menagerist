<script lang="ts">
	import type { Snippet } from 'svelte';
	import { MediaQuery } from 'svelte/reactivity';
	import { mergeProps } from 'bits-ui';
	import { Button, type ButtonProps } from '$lib/components/ui/button/index.js';
	import * as Tooltip from '$lib/components/ui/tooltip/index.js';
	import { cn } from '$lib/utils.js';

	const isTouch = new MediaQuery('any-hover: none', false);

	// The label is the accessible name on every device. A mouse sees only the icon and a tooltip;
	// touch devices have no hover, so they get the label beside the icon at the 44px target size.
	let {
		label,
		shortcut,
		ref = $bindable(null),
		labelOnTouch = true,
		variant = 'ghost',
		class: className,
		children,
		...restProps
	}: Omit<ButtonProps, 'children' | 'size'> & {
		label: string;
		shortcut?: string;
		/** Show the label beside the icon on touch devices; turn off where the bar is too narrow. */
		labelOnTouch?: boolean;
		children?: Snippet;
	} = $props();
</script>

{#snippet face(props: Record<string, unknown>)}
	<Button
		{...mergeProps(props, restProps)}
		bind:ref
		{variant}
		size="icon"
		class={cn(
			labelOnTouch
				? 'pointer-coarse:h-11 pointer-coarse:w-auto pointer-coarse:gap-1.5 pointer-coarse:px-3'
				: 'pointer-coarse:size-11',
			className
		)}
	>
		{@render children?.()}
		<span class={cn('sr-only', labelOnTouch && 'pointer-coarse:not-sr-only')}>{label}</span>
	</Button>
{/snippet}

<!-- A button is already interactive and named, so touch screens get no tooltip or popover for it. -->
{#if isTouch.current}
	{@render face({})}
{:else}
	<Tooltip.Root>
		<Tooltip.Trigger>
			{#snippet child({ props })}
				{@render face(props)}
			{/snippet}
		</Tooltip.Trigger>
		<Tooltip.Content>
			{label}
			{#if shortcut}
				<kbd data-slot="kbd" class="rounded-md bg-background/20 px-1 font-mono text-[10px]"
					>{shortcut}</kbd
				>
			{/if}
		</Tooltip.Content>
	</Tooltip.Root>
{/if}
