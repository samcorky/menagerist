<script lang="ts" module>
	export interface DataTableColumn {
		label: string;
		/** Right-align the column, for row actions. */
		end?: boolean;
		/** The key the list route sorts this column by; the header becomes a button when set. */
		sortKey?: string;
	}
</script>

<script lang="ts">
	import type { Snippet } from 'svelte';
	import { ArrowDown, ArrowUp, ChevronsUpDown } from '@lucide/svelte';
	import * as Table from '$lib/components/ui/table/index.js';
	import { ariaSort, type TableSort } from '$lib/table-sort';

	let {
		label,
		columns,
		sort = null,
		onsort,
		busy = false,
		children
	}: {
		/** Accessible name of the table. */
		label: string;
		columns: DataTableColumn[];
		/** How the table is sorted now; null for the server's own order. */
		sort?: TableSort | null;
		/** A click on a sortable header, with its key. The owner of the rows does the sorting. */
		onsort?: (key: string) => void;
		/** The rows are being read again: they stay, dimmed, so the table does not jump. */
		busy?: boolean;
		/** The `<Table.Row>`s of the body. */
		children: Snippet;
	} = $props();
</script>

<!-- The desktop counterpart of a card list; pair it with `wide` from `$lib/viewport.svelte`. -->
<div class="overflow-hidden rounded-xl border bg-card">
	<Table.Root
		aria-label={label}
		class="text-left [&_td]:px-4 [&_td]:py-2 [&_td]:align-top [&_td]:whitespace-normal"
	>
		<Table.Header class="bg-muted/40">
			<Table.Row class="hover:bg-transparent">
				{#each columns as column (column.label)}
					{@const key = onsort ? column.sortKey : undefined}
					<Table.Head
						scope="col"
						aria-sort={key ? ariaSort(sort, key) : undefined}
						class="h-auto px-4 py-2 text-xs font-medium text-muted-foreground uppercase {column.end
							? 'text-right'
							: ''}"
					>
						{#if key}
							<button
								type="button"
								class="-mx-1 inline-flex items-center gap-1 rounded px-1 py-0.5 uppercase hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none {sort?.key ===
								key
									? 'text-foreground'
									: ''}"
								onclick={() => onsort?.(key)}
							>
								{column.label}
								{#if sort?.key === key}
									{#if sort.order === 'asc'}
										<ArrowUp class="size-3.5" aria-hidden="true" />
									{:else}
										<ArrowDown class="size-3.5" aria-hidden="true" />
									{/if}
								{:else}
									<ChevronsUpDown class="size-3.5 opacity-40" aria-hidden="true" />
								{/if}
							</button>
						{:else}
							{column.label}
						{/if}
					</Table.Head>
				{/each}
			</Table.Row>
		</Table.Header>
		<Table.Body
			aria-busy={busy}
			class={busy ? 'opacity-60 transition-opacity' : 'transition-opacity'}
		>
			{@render children()}
		</Table.Body>
	</Table.Root>
</div>
