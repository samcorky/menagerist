<script lang="ts">
	import { TriangleAlert, X } from '@lucide/svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import { chipModels, missingItemFieldPaths } from '$lib/query/builder';
	import type { Catalogue } from '$lib/query/fields';
	import type { SummaryLookup } from '$lib/query/summary';
	import type { Path, Query } from '$lib/query/types';

	let {
		query,
		lookup,
		warned = new Set<string>(),
		catalogue,
		onopen,
		onremove,
		onclear
	}: {
		query: Query;
		lookup: SummaryLookup;
		warned?: ReadonlySet<string>;
		/** Lets chips for per-item fields that no item has be flagged too. */
		catalogue?: Catalogue;
		/** Open the panel at a row. */
		onopen: (path: Path) => void;
		onremove: (path: Path, text: string) => void;
		onclear: () => void;
	} = $props();

	const allWarned = $derived(
		catalogue ? new Set([...warned, ...missingItemFieldPaths(query, catalogue)]) : warned
	);
	const model = $derived(chipModels(query, lookup, allWarned));
	const notes = $derived([...new Set(model.chips.flatMap((c) => (c.message ? [c.message] : [])))]);
	const noteId = $props.id();
</script>

{#if model.chips.length > 0}
	<div class="flex flex-col gap-2">
		<ul class="flex flex-wrap items-center gap-2" aria-label="Active filters">
			{#if model.lead}
				<li class="text-sm text-muted-foreground">{model.lead}</li>
			{/if}
			{#each model.chips as chip (chip.key)}
				<li
					class="flex max-w-full min-w-0 items-center rounded-full border bg-secondary text-sm text-secondary-foreground {chip.warning
						? 'border-destructive/50'
						: 'border-transparent'}"
				>
					<button
						type="button"
						class="flex min-h-9 min-w-0 items-center gap-1.5 rounded-full py-1 pl-3 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
						title={chip.text}
						aria-describedby={chip.warning ? noteId : undefined}
						onclick={() => onopen(chip.focus)}
					>
						{#if chip.warning}
							<TriangleAlert class="size-4 shrink-0 text-destructive" aria-label="Warning" />
						{/if}
						<span class="truncate">{chip.text}</span>
					</button>
					<button
						type="button"
						class="relative mr-1 ml-0.5 shrink-0 rounded-full p-1.5 after:absolute after:-inset-1.5 after:content-[''] hover:bg-foreground/10 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
						aria-label="Remove filter: {chip.text}"
						onclick={() => onremove(chip.path, chip.text)}
					>
						<X class="size-3.5" />
					</button>
				</li>
			{/each}
			<li>
				<Button variant="ghost" size="sm" class="min-h-9" onclick={onclear}>Clear filters</Button>
			</li>
		</ul>
		{#if notes.length > 0}
			<p id={noteId} class="flex items-start gap-1.5 text-sm">
				<TriangleAlert class="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden="true" />
				{notes.join(' ')}
			</p>
		{/if}
	</div>
{/if}
