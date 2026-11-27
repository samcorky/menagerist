<script lang="ts" generics="T">
	import type { Snippet } from 'svelte';
	import DataTable, { type DataTableColumn } from '$lib/components/data-table.svelte';
	import LoadFailed from '$lib/components/load-failed.svelte';
	import PageNav from '$lib/components/page-nav.svelte';
	import { Skeleton } from '$lib/components/ui/skeleton/index.js';
	import { listTableState } from '$lib/list-table';
	import type { PagedFoot } from '$lib/paged-list.svelte';
	import type { TableSort } from '$lib/table-sort';
	import { wide } from '$lib/viewport.svelte';

	/**
	 * A table on desktop and a list of cards on a phone, with every state a list has (design
	 * §11, §19): a skeleton on the first load, a failure with Try again, an empty message, and
	 * the rows. While a sort, search or page is read again the rows stay on screen, dimmed, so
	 * the page does not collapse and jump; the empty state waits for a finished read. A `list`
	 * adds the page foot of a `PagedList` in `page` mode.
	 */
	let {
		label,
		columns,
		rows,
		rowKey,
		loading,
		failed = false,
		what,
		onretry,
		empty,
		sort = null,
		onsort,
		list,
		noun,
		skeletons = 2,
		row,
		card
	}: {
		/** Accessible name of the table and of the card list. */
		label: string;
		columns: DataTableColumn[];
		rows: readonly T[];
		rowKey: (item: T) => string;
		/** A read is in flight, first or again. */
		loading: boolean;
		/** The first read failed. */
		failed?: boolean;
		/** What failed to load, for "Couldn't load {what}": "your tokens". */
		what: string;
		onretry: () => void;
		/** The sentence for a list with nothing in it. */
		empty: string;
		sort?: TableSort | null;
		onsort?: (key: string) => void;
		/** A `PagedList` in `page` mode, for the Previous and Next foot. */
		list?: PagedFoot;
		/** What a row is, singular, for the foot: "token". Required with `list`. */
		noun?: string;
		/** How many skeleton cards to draw on the first load. */
		skeletons?: number;
		/** One `<Table.Row>` for the desktop table. */
		row: Snippet<[T]>;
		/** The content of one card for a phone, inside its `<li>`. */
		card: Snippet<[T]>;
	} = $props();

	const view = $derived(listTableState({ error: failed, loading, rows: rows.length }));
</script>

{#if view === 'error'}
	<LoadFailed {what} {onretry} />
{:else if view === 'loading'}
	<div class="space-y-3" role="status" aria-label="Loading {what}">
		{#each Array.from({ length: skeletons }, (_, i) => i) as n (n)}
			<Skeleton class="h-20 w-full rounded-xl" />
		{/each}
	</div>
{:else if view === 'empty'}
	<p class="text-sm text-muted-foreground">{empty}</p>
{:else}
	{#if wide.current}
		<DataTable {label} {columns} {sort} {onsort} busy={loading}>
			{#each rows as item (rowKey(item))}
				{@render row(item)}
			{/each}
		</DataTable>
	{:else}
		<ul
			class="space-y-3 transition-opacity {loading ? 'opacity-60' : ''}"
			aria-label={label}
			aria-busy={loading}
		>
			{#each rows as item (rowKey(item))}
				<li>{@render card(item)}</li>
			{/each}
		</ul>
	{/if}
	{#if list && noun}
		<PageNav {list} {noun} />
	{/if}
{/if}
