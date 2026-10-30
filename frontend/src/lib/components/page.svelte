<script lang="ts">
	import { getContext, type Snippet } from 'svelte';
	import { cn } from '$lib/utils.js';
	import { PAGE_ALIGN, type PageAlignSource } from '$lib/page-context';

	// fluid: grids and tables use the screen; reading: item detail and lists; form: short forms;
	// narrow: sign-in and setup. Fluid stops at 2200px so ultrawide screens do not stretch tiles.
	const WIDTHS = {
		fluid: 'max-w-[2200px]',
		reading: 'max-w-5xl',
		form: 'max-w-3xl',
		narrow: 'max-w-sm'
	} as const;

	let {
		width = 'reading',
		class: className,
		children
	}: { width?: keyof typeof WIDTHS; class?: string; children?: Snippet } = $props();

	const alignSource = getContext<PageAlignSource | undefined>(PAGE_ALIGN);
	const align = $derived(alignSource?.current ?? 'center');
</script>

<main class="flex-1 px-4 py-4 sm:px-6 md:py-5">
	<div
		class={cn(
			'flex w-full flex-col gap-4',
			WIDTHS[width],
			align === 'center' && 'mx-auto',
			className
		)}
	>
		{@render children?.()}
	</div>
</main>
