<script lang="ts">
	import type { Snippet } from 'svelte';
	import { ChevronDown } from '@lucide/svelte';
	import * as Collapsible from '$lib/components/ui/collapsible/index.js';
	import { readFlag, writeFlag } from '$lib/remembered';
	import { cn } from '$lib/utils.js';

	// A titled group that can be folded away. The open state is remembered per device under `id`;
	// `forceOpen` (the group holds the current page) wins over a remembered "closed" on first render.
	// `bare` folds the heading away (animated) and shows the content whatever the open state, which
	// the sidebar uses for its icon-only rail.
	let {
		id,
		title,
		count,
		defaultOpen = true,
		forceOpen = false,
		bare = false,
		heading = 'h2',
		titleClass = 'font-heading text-lg font-semibold',
		class: className,
		actions,
		children
	}: {
		id: string;
		title: string;
		count?: number;
		defaultOpen?: boolean;
		forceOpen?: boolean;
		bare?: boolean;
		heading?: 'h2' | 'h3' | 'p';
		titleClass?: string;
		class?: string;
		actions?: Snippet;
		children?: Snippet;
	} = $props();

	// The props only seed the first state; the open state is the user's from then on.
	// svelte-ignore state_referenced_locally
	let open = $state(forceOpen || readFlag(`section:${id}`, defaultOpen));

	// Only a change the person makes animates; a section that starts open (a sidebar opening, a page
	// loading) is simply there, instead of dropping down every time it is created.
	let animated = $state(false);

	function onOpenChange(value: boolean) {
		animated = true;
		open = value;
		writeFlag(`section:${id}`, value);
	}
</script>

<Collapsible.Root
	open={open || bare}
	{onOpenChange}
	class={cn('flex min-w-0 flex-col gap-2', className)}
>
	<div
		class={cn(
			'grid transition-[grid-template-rows,opacity] duration-200 motion-reduce:transition-none',
			bare ? 'grid-rows-[0fr] opacity-0' : 'grid-rows-[1fr]'
		)}
		inert={bare}
	>
		<div class="flex min-h-0 items-center justify-between gap-2 overflow-hidden">
			<!-- The heading wraps the toggle (not the other way round), so it stays a heading for screen
			     readers; a plain paragraph is used where the title is not a section heading. -->
			<svelte:element this={heading} class="min-w-0">
				<Collapsible.Trigger
					aria-expanded={open}
					class="group -ml-1 flex min-w-0 items-center gap-1.5 rounded-lg px-1 py-0.5 text-left outline-none focus-visible:ring-3 focus-visible:ring-ring/30"
				>
					<ChevronDown
						class={cn(
							'size-4 shrink-0 text-muted-foreground transition-transform motion-reduce:transition-none',
							!open && '-rotate-90'
						)}
					/>
					<span class={titleClass}>{title}</span>
					{#if count !== undefined}
						<span class="text-sm text-muted-foreground tabular-nums">{count}</span>
					{/if}
				</Collapsible.Trigger>
			</svelte:element>
			{@render actions?.()}
		</div>
	</div>
	<Collapsible.Content
		class={cn(
			'-m-1 min-w-0 overflow-hidden p-1',
			animated &&
				'data-[state=closed]:animate-collapsible-up data-[state=open]:animate-collapsible-down motion-reduce:animate-none'
		)}
	>
		{@render children?.()}
	</Collapsible.Content>
</Collapsible.Root>
