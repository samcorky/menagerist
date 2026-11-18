<script lang="ts">
	import { Button } from '$lib/components/ui/button/index.js';
	import { Spinner } from '$lib/components/ui/spinner/index.js';
	import { RefreshCw } from '@lucide/svelte';
	import { endMessage, listEndState, loadAheadMargin, LOAD_MORE_FAILED } from '$lib/list-end';

	/**
	 * The foot of an infinite list (#588): the sentinel that loads the next page, the
	 * spinner while it loads, the end-of-list message with its count, and a retry when
	 * a page would not load. Every paging list uses this instead of its own observer.
	 *
	 * The next page starts loading well before the foot comes into view (§19), so a
	 * steady scroller rarely waits. The state is announced politely, never by moving
	 * focus (§20a).
	 */
	let {
		loading,
		hasMore,
		rows,
		total = null,
		noun,
		lines = [],
		lineKey,
		failed = false,
		onload,
		onretry
	}: {
		loading: boolean;
		hasMore: boolean;
		/** How many rows are on screen: the first page shows a skeleton, not this (§13a). */
		rows: number;
		/** The server's count, where the list has one; otherwise the rows are counted. */
		total?: number | null;
		/** What the list holds, singular: "item", "collection", "item type". */
		noun: string;
		/** Optional flavour lines for the end of a long list, in the spirit of #102. */
		lines?: readonly string[];
		/** Keys the flavour line so it stays put for this list within a session. */
		lineKey?: string;
		/** The next page failed; shown as a retry rather than a silent stop. */
		failed?: boolean;
		onload: () => void;
		onretry?: () => void;
	} = $props();

	const state = $derived(listEndState({ loading, hasMore, failed, rows }));
	const ending = $derived(
		state === 'end' ? endMessage(rows, total, noun, lines, lineKey ?? noun) : ''
	);
	// What a screen reader hears. The end message is wordy; the spinner needs a plain line.
	const announcement = $derived(
		state === 'loading' ? 'Loading more…' : state === 'end' ? ending : ''
	);

	function sentinel(node: HTMLElement) {
		let observer: IntersectionObserver | undefined;

		// The margin follows the viewport, so a tall window loads further ahead than a phone.
		function observe() {
			observer?.disconnect();
			observer = new IntersectionObserver(
				(entries) => {
					if (entries[0].isIntersecting) onload();
				},
				{ rootMargin: loadAheadMargin(window.innerHeight) }
			);
			observer.observe(node);
		}

		observe();
		window.addEventListener('resize', observe);
		return {
			destroy() {
				window.removeEventListener('resize', observe);
				observer?.disconnect();
			}
		};
	}
</script>

<div data-slot="list-foot" class="flex flex-col items-center gap-3 py-4">
	{#if hasMore && !failed}
		<!-- Only the sentinel is hidden from the reader; the live region below speaks for it. -->
		<div use:sentinel aria-hidden="true" class="flex justify-center">
			{#if state === 'loading'}
				<Spinner class="size-5 text-muted-foreground" aria-label={null} />
			{/if}
		</div>
	{:else if state === 'failed'}
		<p class="text-sm text-muted-foreground">{LOAD_MORE_FAILED}</p>
		{#if onretry}
			<Button variant="outline" size="sm" onclick={onretry}>
				<RefreshCw class="size-3.5" />
				Try again
			</Button>
		{/if}
	{:else if state === 'end'}
		<p data-testid="list-end" class="text-sm text-muted-foreground">{ending}</p>
	{/if}
</div>

<p class="sr-only" role="status" aria-live="polite">{announcement}</p>
