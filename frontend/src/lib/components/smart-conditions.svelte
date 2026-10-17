<script lang="ts">
	import { TriangleAlert } from '@lucide/svelte';
	import type { SummaryLookup } from '$lib/query/summary';
	import type { SearchWarning } from '$lib/query/search';
	import { UNREADABLE_CONDITIONS_MESSAGE, smartCollectionSummary } from '$lib/smart-collections';

	let {
		definition,
		lookup,
		warnings = []
	}: {
		/** The stored definition, as the server sent it. */
		definition: unknown;
		lookup: SummaryLookup;
		warnings?: SearchWarning[];
	} = $props();

	const summary = $derived(smartCollectionSummary(definition, lookup, warnings));
	const notes = $derived(
		summary ? [...new Set(summary.chips.flatMap((c) => (c.message ? [c.message] : [])))] : []
	);
</script>

{#if !summary}
	<p class="text-sm text-muted-foreground">{UNREADABLE_CONDITIONS_MESSAGE}</p>
{:else if summary.chips.length > 0}
	<div class="flex flex-col gap-2">
		<ul class="flex flex-wrap items-center gap-2" aria-label="Conditions">
			{#if summary.lead}
				<li class="text-sm text-muted-foreground">{summary.lead}</li>
			{/if}
			{#each summary.chips as chip (chip.key)}
				<li
					class="flex max-w-full min-w-0 items-center gap-1.5 rounded-full border bg-secondary px-3 py-1 text-sm text-secondary-foreground {chip.warning
						? 'border-destructive/50'
						: 'border-transparent'}"
					title={chip.text}
				>
					{#if chip.warning}
						<TriangleAlert class="size-4 shrink-0 text-destructive" aria-label="Warning" />
					{/if}
					<span class="truncate">{chip.text}</span>
				</li>
			{/each}
		</ul>
		{#if notes.length > 0}
			<p class="flex items-start gap-1.5 text-sm">
				<TriangleAlert class="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden="true" />
				{notes.join(' ')}
			</p>
		{/if}
	</div>
{/if}
