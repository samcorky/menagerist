<script lang="ts">
	import { Button } from '$lib/components/ui/button/index.js';
	import { ChevronLeft, ChevronRight, RefreshCw } from '@lucide/svelte';
	import { LOAD_MORE_FAILED, pageRangeMessage } from '$lib/list-end';
	import type { PagedFoot } from '$lib/paged-list.svelte';

	/**
	 * The foot of a table, or of one of several lists on a screen (design §19): where this
	 * page sits in the list, Previous and Next, and a plain retry for a page that would not
	 * load. It is the counterpart of `ListFoot` for a `PagedList` in `page` mode; a list that
	 * is the main thing on its page scrolls instead.
	 *
	 * A list that fits one page shows only how many rows it holds. The range is announced
	 * politely, never by moving focus (§20a), and the buttons keep their place while the next
	 * page loads, so a keyboard user can press again.
	 */
	let {
		list,
		noun
	}: {
		list: PagedFoot;
		/** What the list holds, singular: "session", "user", "backup". */
		noun: string;
	} = $props();

	const from = $derived(list.from);
	const to = $derived(list.to);
	const single = $derived(list.pageIndex === 0 && !list.hasMore);
	const range = $derived(
		from === null || to === null ? '' : pageRangeMessage(from, to, list.total, noun, single)
	);
	const label = $derived(`${noun[0].toUpperCase()}${noun.slice(1)} pages`);
</script>

{#if list.rows.length > 0 || list.nextFailed}
	<nav
		aria-label={label}
		aria-busy={list.loading}
		data-slot="page-nav"
		class="flex flex-wrap items-center justify-between gap-3 py-3"
	>
		{#if list.nextFailed}
			<p class="text-sm text-muted-foreground">{LOAD_MORE_FAILED}</p>
			<Button variant="outline" size="sm" onclick={() => void list.retry()}>
				<RefreshCw class="size-3.5" />
				Try again
			</Button>
		{:else}
			<p data-testid="page-range" class="text-sm text-muted-foreground">{range}</p>
			{#if !single}
				<div class="flex gap-2">
					<Button
						variant="outline"
						size="sm"
						disabled={list.pageIndex === 0 || list.loading}
						onclick={() => void list.previous()}
					>
						<ChevronLeft class="size-4" />
						Previous
					</Button>
					<Button
						variant="outline"
						size="sm"
						disabled={!list.hasMore || list.loading}
						onclick={() => void list.next()}
					>
						Next
						<ChevronRight class="size-4" />
					</Button>
				</div>
			{/if}
		{/if}
	</nav>
	<p class="sr-only" role="status" aria-live="polite">{list.nextFailed ? '' : range}</p>
{/if}
