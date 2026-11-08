<script lang="ts">
	import { Progress } from '$lib/components/ui/progress/index.js';
	import { cn } from '$lib/utils.js';

	let {
		percent,
		label,
		compact = false,
		showPercent = true,
		class: className
	}: {
		/** Whole-number completion from 0 to 100. */
		percent: number;
		/** What the bar measures, as its accessible name. */
		label: string;
		compact?: boolean;
		showPercent?: boolean;
		class?: string;
	} = $props();
</script>

<div class={cn('flex items-center gap-3', className)}>
	<Progress value={percent} max={100} aria-label={label} class={compact ? 'h-1.5' : 'h-2'} />
	{#if showPercent}
		<span
			class={cn(
				'shrink-0 text-right text-muted-foreground tabular-nums',
				compact ? 'w-9 text-xs' : 'w-10 text-sm'
			)}
		>
			{percent}%
		</span>
	{/if}
</div>
