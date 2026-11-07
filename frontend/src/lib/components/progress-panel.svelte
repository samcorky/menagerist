<script lang="ts">
	import { Check, Circle } from '@lucide/svelte';
	import type { ProgressSnapshotResponse } from '$lib/api/client';
	import ProgressBar from '$lib/components/progress-bar.svelte';
	import { Spinner } from '$lib/components/ui/spinner/index.js';
	import { headline, markLabel, percentOf, phaseCounts, phaseMark } from '$lib/progress';

	let {
		snapshot,
		label,
		fallback
	}: {
		/** The latest progress, or null before anything has been reported. */
		snapshot: ProgressSnapshotResponse | null;
		/** What the bar measures, as its accessible name. */
		label: string;
		/** What to say before the first phase starts, such as while a file arrives. */
		fallback: string;
	} = $props();

	const percent = $derived(snapshot ? percentOf(snapshot) : 0);
</script>

<div class="space-y-3">
	<ProgressBar {percent} {label} />
	<!-- Only the phase is announced; counts change every second and stay out of it. -->
	<p class="text-sm font-medium" aria-live="polite">{headline(snapshot, fallback)}</p>
	{#if snapshot && snapshot.phases.length > 0}
		<ol class="space-y-1.5 text-sm" aria-label="Steps">
			{#each snapshot.phases as phase (phase.key)}
				{@const mark = phaseMark(phase)}
				{@const counted = phaseCounts(phase)}
				<li class="flex items-center gap-2" aria-current={mark === 'current' ? 'step' : undefined}>
					{#if mark === 'done'}
						<Check class="size-4 shrink-0 text-primary" aria-hidden="true" />
					{:else if mark === 'current'}
						<Spinner class="size-4 shrink-0 motion-reduce:animate-none" aria-hidden="true" />
					{:else}
						<Circle class="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
					{/if}
					<span class={mark === 'waiting' ? 'text-muted-foreground' : undefined}>
						{phase.label}
					</span>
					{#if mark === 'current' && counted}
						<span class="text-muted-foreground">({counted})</span>
					{/if}
					<span class="sr-only">{markLabel(mark)}</span>
				</li>
			{/each}
		</ol>
	{/if}
</div>
