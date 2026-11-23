<script lang="ts">
	import type { Snippet } from 'svelte';
	import { X } from '@lucide/svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Checkbox } from '$lib/components/ui/checkbox/index.js';
	import { OFFLINE_DESCRIPTION, OFFLINE_TITLE } from '$lib/offline';
	import { offlineController } from '$lib/offline.svelte.js';
	import { selectionSummary, visibleCheckState } from '$lib/selection-summary';

	let {
		count,
		hidden,
		limit,
		visibleSelected,
		visibleTotal,
		ontogglevisible,
		onclear,
		onexit,
		actions
	}: {
		/** Everything selected, including what the current view hides. */
		count: number;
		/** Selected items the current search or filter does not show. */
		hidden: number;
		limit: number;
		/** How many of the rows in view are selected, and how many rows are in view. */
		visibleSelected: number;
		visibleTotal: number;
		ontogglevisible: () => void;
		/** Drop every selection, hidden ones too, and stay in selection mode. */
		onclear: () => void;
		/** Leave selection mode. Changes nothing else. */
		onexit: () => void;
		/** The page's action buttons; they are disabled while offline. */
		actions: Snippet<[{ disabled: boolean }]>;
	} = $props();

	const offline = $derived(offlineController.offline);
	const checkState = $derived(visibleCheckState(visibleSelected, visibleTotal));
	const summary = $derived(selectionSummary(count, hidden, limit));
</script>

<div
	data-testid="selection-bar"
	role="toolbar"
	aria-label="Actions for selected items"
	class="sticky bottom-2 z-30 flex flex-col gap-2 rounded-2xl border bg-background/95 p-2 shadow-lg backdrop-blur md:top-2 md:bottom-auto"
>
	<div class="flex flex-wrap items-center gap-x-3 gap-y-1 px-1">
		<label class="flex items-center gap-2 text-sm font-medium pointer-coarse:min-h-11">
			<Checkbox
				aria-label="Select all"
				checked={checkState === 'checked'}
				indeterminate={checkState === 'indeterminate'}
				disabled={visibleTotal === 0}
				onCheckedChange={() => ontogglevisible()}
			/>
			Select all
		</label>
		<p class="flex-1 text-sm whitespace-nowrap" aria-live="polite" data-testid="selection-count">
			{summary}
		</p>
		{#if count > 0}
			<Button variant="ghost" size="sm" class="pointer-coarse:h-11" onclick={onclear}>Clear</Button>
		{/if}
		<Button variant="ghost" size="sm" class="pointer-coarse:h-11" onclick={onexit}>
			<X />
			Done
		</Button>
	</div>
	<div class="flex flex-wrap gap-2">
		{@render actions({ disabled: offline || count === 0 })}
	</div>
	{#if offline}
		<p class="px-1 text-xs text-muted-foreground">{OFFLINE_TITLE}. {OFFLINE_DESCRIPTION}</p>
	{/if}
</div>
